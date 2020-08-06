import asyncio

import aiofiles
import pytest

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient


class CustomMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Custom-Header"] = "Example"
        return response


app = Starlette()
app.add_middleware(CustomMiddleware)


@app.route("/")
def homepage(request):
    return PlainTextResponse("Homepage")


@app.route("/exc")
def exc(request):
    raise Exception()


@app.route("/no-response")
class NoResponse:
    def __init__(self, scope, receive, send):
        pass

    def __await__(self):
        return self.dispatch().__await__()

    async def dispatch(self):
        pass


@app.websocket_route("/ws")
async def websocket_endpoint(session):
    await session.accept()
    await session.send_text("Hello, world!")
    await session.close()


def test_custom_middleware():
    client = TestClient(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"

    with pytest.raises(Exception):
        response = client.get("/exc")

    with pytest.raises(RuntimeError):
        response = client.get("/no-response")

    with client.websocket_connect("/ws") as session:
        text = session.receive_text()
        assert text == "Hello, world!"


def test_middleware_decorator():
    app = Starlette()

    @app.route("/homepage")
    def homepage(request):
        return PlainTextResponse("Homepage")

    @app.middleware("http")
    async def plaintext(request, call_next):
        if request.url.path == "/":
            return PlainTextResponse("OK")
        response = await call_next(request)
        response.headers["Custom"] = "Example"
        return response

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "OK"

    response = client.get("/homepage")
    assert response.text == "Homepage"
    assert response.headers["Custom"] == "Example"


def test_state_data_across_multiple_middlewares():
    expected_value1 = "foo"
    expected_value2 = "bar"

    class aMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.foo = expected_value1
            response = await call_next(request)
            return response

    class bMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.bar = expected_value2
            response = await call_next(request)
            response.headers["X-State-Foo"] = request.state.foo
            return response

    class cMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["X-State-Bar"] = request.state.bar
            return response

    app = Starlette()
    app.add_middleware(aMiddleware)
    app.add_middleware(bMiddleware)
    app.add_middleware(cMiddleware)

    @app.route("/")
    def homepage(request):
        return PlainTextResponse("OK")

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "OK"
    assert response.headers["X-State-Foo"] == expected_value1
    assert response.headers["X-State-Bar"] == expected_value2


def test_app_middleware_argument():
    def homepage(request):
        return PlainTextResponse("Homepage")

    app = Starlette(
        routes=[Route("/", homepage)], middleware=[Middleware(CustomMiddleware)]
    )

    client = TestClient(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"


def test_middleware_repr():
    middleware = Middleware(CustomMiddleware)
    assert repr(middleware) == "Middleware(CustomMiddleware)"


@app.route("/streaming")
async def some_streaming(_):
    async def numbers_stream():
        """
        Should produce something like:
             <html><body><ul><li>1...</li></ul></body></html>
        """
        yield ("<html><body><ul>")
        for number in range(1, 4):
            yield "<li>%d</li>" % number
        yield ("</ul></body></html>")

    return StreamingResponse(numbers_stream())


@app.route("/broken-streaming-on-start")
async def broken_stream_start(request):
    async def broken():
        raise ValueError("Oh no!")
        yield 0  # pragma: no cover

    return StreamingResponse(broken())


@app.route("/broken-streaming-midstream")
async def broken_stream_midstream(request):
    async def broken():
        yield ("<html><body><ul>")
        for number in range(1, 3):
            yield "<li>%d</li>" % number
            if number >= 2:
                raise RuntimeError("This is a broken stream")

    return StreamingResponse(broken())


@app.route("/background-after-streaming")
async def background_after_streaming(request):
    filepath = request.query_params["filepath"]

    async def background():
        await asyncio.sleep(1)
        async with aiofiles.open(filepath, mode="w") as fl:  # pragma: no cover
            await fl.write("background last")

    async def numbers_stream():
        async with aiofiles.open(filepath, mode="w") as fl:
            await fl.write("handler first")
        for number in range(1, 4):
            yield "%d\n" % number

    return StreamingResponse(numbers_stream(), background=BackgroundTask(background))


def test_custom_middleware_streaming(tmp_path):
    client = TestClient(app)
    response = client.get("/streaming")
    assert response.headers["Custom-Header"] == "Example"
    assert (
        response.text
        == "<html><body><ul><li>1</li><li>2</li><li>3</li></ul></body></html>"
    )

    with pytest.raises(RuntimeError):
        # after body streaming has started
        response = client.get("/broken-streaming-midstream")
    with pytest.raises(ValueError):
        # right before body stream starts (only start message emitted)
        # this should trigger _first_ message being None
        response = client.get("/broken-streaming-on-start")

    filepath = tmp_path / "background_test.txt"
    filepath.write_text("Test Start")
    response = client.get("/background-after-streaming?filepath={}".format(filepath))
    assert response.headers["Custom-Header"] == "Example"
    assert response.text == "1\n2\n3\n"
    with filepath.open() as fl:
        assert fl.read() == "handler first"

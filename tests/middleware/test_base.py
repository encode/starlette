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


def test_custom_middleware_streaming(tmp_path):
    """
    Ensure that a StreamingResponse completes successfully with BaseHTTPMiddleware
    """

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

    client = TestClient(app)
    response = client.get("/streaming")
    assert response.headers["Custom-Header"] == "Example"
    assert (
        response.text
        == "<html><body><ul><li>1</li><li>2</li><li>3</li></ul></body></html>"
    )


def test_custom_middleware_streaming_exception_on_start():
    """
    Ensure that BaseHTTPMiddleware handles exceptions on response start
    """

    @app.route("/broken-streaming-on-start")
    async def broken_stream_start(request):
        async def broken():
            raise ValueError("Oh no!")
            yield 0  # pragma: no cover

        return StreamingResponse(broken())

    client = TestClient(app)
    with pytest.raises(ValueError):
        # right before body stream starts (only start message emitted)
        # this should trigger _first_ message being None
        response = client.get("/broken-streaming-on-start")


def test_custom_middleware_streaming_exception_midstream():
    """
    Ensure that BaseHTTPMiddleware handles exceptions after streaming has started
    """

    @app.route("/broken-streaming-midstream")
    async def broken_stream_midstream(request):
        async def broken():
            yield ("<html><body><ul>")
            for number in range(1, 3):
                yield "<li>%d</li>" % number
                if number >= 2:
                    raise RuntimeError("This is a broken stream")

        return StreamingResponse(broken())

    client = TestClient(app)
    with pytest.raises(RuntimeError):
        # after body streaming has started
        response = client.get("/broken-streaming-midstream")


def test_custom_middleware_streaming_background(tmp_path):
    """
    Ensure that BaseHTTPMiddleware with a StreamingResponse runs BackgroundTasks after response.

    This test writes to a temporary file
    """

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

        return StreamingResponse(
            numbers_stream(), background=BackgroundTask(background)
        )

    client = TestClient(app)

    # Set up a file to track whether background has run
    filepath = tmp_path / "background_test.txt"
    filepath.write_text("Test Start")

    response = client.get("/background-after-streaming?filepath={}".format(filepath))
    assert response.headers["Custom-Header"] == "Example"
    assert response.text == "1\n2\n3\n"
    with filepath.open() as fl:
        # background should not have run yet
        assert fl.read() == "handler first"


class Custom404Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        if resp.status_code == 404:
            return PlainTextResponse("Oh no!")
        return resp


def test_custom_middleware_pending_tasks(tmp_path):
    """
    Ensure that tasks are not pending left due to call_next method
    """
    app.add_middleware(Custom404Middleware)

    @app.route("/trivial")
    async def trivial(_):
        return PlainTextResponse("Working")

    @app.route("/streaming_task_count")
    async def some_streaming(_):
        async def numbers_stream():
            for number in range(1, 4):
                yield "%d\n" % number

        return StreamingResponse(numbers_stream())

    client = TestClient(app)
    task_count = lambda: len(asyncio.Task.all_tasks())
    # Task_count after issuing requests must not grow
    assert task_count() == 1
    response = client.get("/missing")
    assert task_count() <= 2
    response = client.get("/missing")
    assert task_count() <= 2
    response = client.get("/trivial")
    assert task_count() <= 2
    response = client.get("/streaming_task_count")
    assert response.text == "1\n2\n3\n"
    assert task_count() <= 2
    response = client.get("/missing")
    assert task_count() <= 2
    response = client.get("/trivial")
    assert response.text == "Working"

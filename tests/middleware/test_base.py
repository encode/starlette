import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
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


class CustomRequest(Request):
    pass


class BadCustomRequest:
    pass


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
        response.headers["X-Request-Class"] = request.__class__.__name__
        return response

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "OK"

    response = client.get("/homepage")
    assert response.text == "Homepage"
    assert response.headers["Custom"] == "Example"
    assert response.headers["X-Request-Class"] == "Request"


def test_middleware_decorator_custom_req():
    app = Starlette()

    @app.route("/custom-request")
    def custom_req(request):
        return PlainTextResponse(request.__class__.__name__)

    @app.middleware("http")
    async def plaintext(request: CustomRequest, call_next):
        response = await call_next(request)
        response.headers["Custom"] = "Example"
        response.headers["X-Request-Class"] = request.__class__.__name__
        return response

    client = TestClient(app)

    response = client.get("/custom-request")
    assert response.text == "Request"
    assert response.headers["X-Request-Class"] == "CustomRequest"


def test_middleware_decorator_custom_req_fails():
    app = Starlette()

    @app.route("/bad-custom-request")
    def custom_req(request):  # pragma: no cover
        return PlainTextResponse(request.__class__.__name__)

    @app.middleware("http")
    async def plaintext(request: BadCustomRequest, call_next):  # pragma: no cover
        response = await call_next(request)
        response.headers["Custom"] = "Example"
        response.headers["X-Request-Class"] = request.__class__.__name__
        return response

    client = TestClient(app)
    with pytest.raises(TypeError):
        client.get("/bad-custom-request")


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

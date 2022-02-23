import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Mount, Route, WebSocketRoute


class CustomMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Custom-Header"] = "Example"
        return response


def homepage(request):
    return PlainTextResponse("Homepage")


def exc(request):
    raise Exception("Exc")


def exc_stream(request):
    return StreamingResponse(_generate_faulty_stream())


def _generate_faulty_stream():
    yield b"Ok"
    raise Exception("Faulty Stream")


class NoResponse:
    def __init__(self, scope, receive, send):
        pass

    def __await__(self):
        return self.dispatch().__await__()

    async def dispatch(self):
        pass


async def websocket_endpoint(session):
    await session.accept()
    await session.send_text("Hello, world!")
    await session.close()


app = Starlette(
    routes=[
        Route("/", endpoint=homepage),
        Route("/exc", endpoint=exc),
        Route("/exc-stream", endpoint=exc_stream),
        Route("/no-response", endpoint=NoResponse),
        WebSocketRoute("/ws", endpoint=websocket_endpoint),
    ],
    middleware=[Middleware(CustomMiddleware)],
)


def test_custom_middleware(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"

    with pytest.raises(Exception) as ctx:
        response = client.get("/exc")
    assert str(ctx.value) == "Exc"

    with pytest.raises(Exception) as ctx:
        response = client.get("/exc-stream")
    assert str(ctx.value) == "Faulty Stream"

    with pytest.raises(RuntimeError):
        response = client.get("/no-response")

    with client.websocket_connect("/ws") as session:
        text = session.receive_text()
        assert text == "Hello, world!"


def test_state_data_across_multiple_middlewares(test_client_factory):
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

    def homepage(request):
        return PlainTextResponse("OK")

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[
            Middleware(aMiddleware),
            Middleware(bMiddleware),
            Middleware(cMiddleware),
        ],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "OK"
    assert response.headers["X-State-Foo"] == expected_value1
    assert response.headers["X-State-Bar"] == expected_value2


def test_app_middleware_argument(test_client_factory):
    def homepage(request):
        return PlainTextResponse("Homepage")

    app = Starlette(
        routes=[Route("/", homepage)], middleware=[Middleware(CustomMiddleware)]
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"


def test_middleware_repr():
    middleware = Middleware(CustomMiddleware)
    assert repr(middleware) == "Middleware(CustomMiddleware)"


def test_fully_evaluated_response(test_client_factory):
    # Test for https://github.com/encode/starlette/issues/1022
    class CustomMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            await call_next(request)
            return PlainTextResponse("Custom")

    app = Starlette(middleware=[Middleware(CustomMiddleware)])

    client = test_client_factory(app)
    response = client.get("/does_not_exist")
    assert response.text == "Custom"


def test_exception_on_mounted_apps(test_client_factory):
    sub_app = Starlette(routes=[Route("/", exc)])
    app = Starlette(routes=[Mount("/sub", app=sub_app)])

    client = test_client_factory(app)
    with pytest.raises(Exception) as ctx:
        client.get("/sub/")
    assert str(ctx.value) == "Exc"


def test_stream_consumed_in_middleware(test_client_factory) -> None:
    class CustomMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            await request.body()
            response = await call_next(request)
            return response  # pragma: no cover

    async def endpoint(request: Request) -> Response:
        await request.body()
        return Response()  # pragma: no cover

    app = Starlette(
        middleware=[Middleware(CustomMiddleware)], routes=[Route("/", endpoint)]
    )

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="Receive stream already consumed"):
        client.get("/")

import contextvars
from typing import AsyncGenerator, Optional

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.http import HTTPMiddleware
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.types import ASGIApp, Receive, Scope, Send


class CustomMiddleware(HTTPMiddleware):
    async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
        response = yield
        response.headers["Custom-Header"] = "Example"


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

    class aMiddleware(HTTPMiddleware):
        async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
            scope["state_foo"] = expected_value1
            yield

    class bMiddleware(HTTPMiddleware):
        async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
            scope["state_bar"] = expected_value2
            response = yield
            response.headers["X-State-Foo"] = scope["state_foo"]

    class cMiddleware(HTTPMiddleware):
        async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
            response = yield
            response.headers["X-State-Bar"] = scope["state_bar"]

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


def test_early_response(test_client_factory):
    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(self, scope: Scope) -> AsyncGenerator[Response, Response]:
            yield Response(status_code=401)

    app = Starlette(middleware=[Middleware(CustomMiddleware)])

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 401


def test_too_many_yields(test_client_factory) -> None:
    class BadMiddleware(HTTPMiddleware):
        async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
            _ = yield
            yield

    app = Starlette(middleware=[Middleware(BadMiddleware)])

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="should yield exactly once"):
        client.get("/")


def test_error_response(test_client_factory) -> None:
    class Failed(Exception):
        pass

    async def failure(request):
        raise Failed()

    class ErrorMiddleware(HTTPMiddleware):
        async def dispatch(
            self, scope: Scope
        ) -> AsyncGenerator[Optional[Response], Response]:
            try:
                yield None
            except Failed:
                yield Response("Failed", status_code=500)

    app = Starlette(
        routes=[Route("/fail", failure)],
        middleware=[Middleware(ErrorMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/fail")
    assert response.text == "Failed"
    assert response.status_code == 500


def test_no_error_response(test_client_factory) -> None:
    class Failed(Exception):
        pass

    async def index(request):
        raise Failed()

    class BadMiddleware(HTTPMiddleware):
        async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
            try:
                yield
            except Failed:
                pass

    app = Starlette(routes=[Route("/", index)], middleware=[Middleware(BadMiddleware)])

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="no response was returned"):
        client.get("/")


ctxvar: contextvars.ContextVar[str] = contextvars.ContextVar("ctxvar")


class PureASGICustomMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        ctxvar.set("set by middleware")
        await self.app(scope, receive, send)
        assert ctxvar.get() == "set by endpoint"


class HTTPCustomMiddleware(HTTPMiddleware):
    async def dispatch(self, scope: Scope) -> AsyncGenerator[None, Response]:
        ctxvar.set("set by middleware")
        yield
        assert ctxvar.get() == "set by endpoint"


@pytest.mark.parametrize(
    "middleware_cls",
    [
        PureASGICustomMiddleware,
        HTTPCustomMiddleware,
    ],
)
def test_contextvars(test_client_factory, middleware_cls: type):
    # this has to be an async endpoint because Starlette calls run_in_threadpool
    # on sync endpoints which has it's own set of peculiarities w.r.t propagating
    # contextvars (it propagates them forwards but not backwards)
    async def homepage(request):
        assert ctxvar.get() == "set by middleware"
        ctxvar.set("set by endpoint")
        return PlainTextResponse("Homepage")

    app = Starlette(
        middleware=[Middleware(middleware_cls)], routes=[Route("/", homepage)]
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200, response.content

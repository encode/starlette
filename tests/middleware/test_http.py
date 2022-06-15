from typing import Any, AsyncGenerator, Callable, Optional

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.http import HTTPMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket


def homepage(request: Request) -> Response:
    return PlainTextResponse("Homepage")


def exc(request: Request) -> Response:
    raise Exception("Exc")


def exc_stream(request: Request) -> Response:
    return StreamingResponse(_generate_faulty_stream())


def _generate_faulty_stream():
    yield b"Ok"
    raise Exception("Faulty Stream")


class NoResponse:
    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        pass

    def __await__(self) -> Any:
        return self.dispatch().__await__()

    async def dispatch(self) -> None:
        pass


async def websocket_endpoint(session: WebSocket):
    await session.accept()
    await session.send_text("Hello, world!")
    await session.close()


class CustomMiddleware(HTTPMiddleware):
    async def dispatch(self, request: HTTPConnection) -> AsyncGenerator[None, Response]:
        response = yield
        response.headers["Custom-Header"] = "Example"


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


def test_custom_middleware(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    client = test_client_factory(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"

    with pytest.raises(Exception) as ctx:
        response = client.get("/exc")
    assert str(ctx.value) == "Exc"

    with pytest.raises(Exception) as ctx:
        response = client.get("/exc-stream")
    assert str(ctx.value) == "Faulty Stream"

    with pytest.raises(AssertionError):  # from TestClient
        response = client.get("/no-response")

    with client.websocket_connect("/ws") as session:
        text = session.receive_text()
        assert text == "Hello, world!"


def test_state_data_across_multiple_middlewares(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    expected_value1 = "foo"
    expected_value2 = "bar"

    async def middleware_a(request: HTTPConnection) -> AsyncGenerator[None, None]:
        request.state.foo = expected_value1
        yield

    async def middleware_b(request: HTTPConnection) -> AsyncGenerator[None, Response]:
        request.state.bar = expected_value2
        response = yield
        response.headers["X-State-Foo"] = request.state.foo

    async def middleware_c(request: HTTPConnection) -> AsyncGenerator[None, Response]:
        response = yield
        response.headers["X-State-Bar"] = request.state.bar

    def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[
            Middleware(HTTPMiddleware, dispatch=middleware_a),
            Middleware(HTTPMiddleware, dispatch=middleware_b),
            Middleware(HTTPMiddleware, dispatch=middleware_c),
        ],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "OK"
    assert response.headers["X-State-Foo"] == expected_value1
    assert response.headers["X-State-Bar"] == expected_value2


def test_dispatch_argument(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    def homepage(request: Request):
        return PlainTextResponse("Homepage")

    async def dispatch(conn: HTTPConnection) -> AsyncGenerator[None, Response]:
        response = yield
        response.headers["Custom-Header"] = "Example"

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[Middleware(HTTPMiddleware, dispatch=dispatch)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"


def test_early_response(test_client_factory: Callable[[ASGIApp], TestClient]) -> None:
    async def index(request: Request):
        return PlainTextResponse("Hello, world!")

    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[Optional[Response], Response]:
            if conn.headers.get("X-Early") == "true":
                yield Response(status_code=401)
            else:
                yield None

    app = Starlette(
        routes=[Route("/", index)],
        middleware=[Middleware(CustomMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "Hello, world!"
    response = client.get("/", headers={"X-Early": "true"})
    assert response.status_code == 401


def test_too_many_yields(test_client_factory: Callable[[ASGIApp], TestClient]) -> None:
    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[None, Response]:
            yield
            yield

    app = Starlette(middleware=[Middleware(CustomMiddleware)])

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="should yield exactly once"):
        client.get("/")


def test_too_many_yields_early_response(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[Optional[Response], Response]:
            yield Response()
            yield None

    app = Starlette(middleware=[Middleware(CustomMiddleware)])

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="should yield exactly once"):
        client.get("/")


def test_error_response(test_client_factory: Callable[[ASGIApp], TestClient]) -> None:
    class Failed(Exception):
        pass

    async def failure(request: Request):
        raise Failed()

    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[Optional[Response], Response]:
            try:
                yield None
            except Failed:
                yield Response("Failed", status_code=500)

    app = Starlette(
        routes=[Route("/fail", failure)],
        middleware=[Middleware(CustomMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/fail")
    assert response.text == "Failed"
    assert response.status_code == 500


def test_no_error_response(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    class Failed(Exception):
        pass

    async def index(request: Request):
        raise Failed()

    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[None, Response]:
            try:
                yield
            except Failed:
                pass

    app = Starlette(
        routes=[Route("/", index)],
        middleware=[Middleware(CustomMiddleware)],
    )

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="no response was returned"):
        client.get("/")


def test_modify_content_type(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    async def dispatch(request: HTTPConnection) -> AsyncGenerator[None, Response]:
        resp = yield
        resp.media_type = "text/csv"

    def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[
            Middleware(HTTPMiddleware, dispatch=dispatch),
        ],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "OK"
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"

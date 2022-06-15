from typing import AsyncGenerator, Callable, Iterator, Optional

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.http import HTTPMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.types import ASGIApp
from starlette.websockets import WebSocket


async def homepage(request: Request) -> Response:
    return PlainTextResponse("Homepage")


async def exc(request: Request) -> Response:
    raise Exception("Exc")


async def exc_stream(request: Request) -> Response:
    return StreamingResponse(_generate_faulty_stream())


def _generate_faulty_stream() -> Iterator[bytes]:
    yield b"Ok"
    raise Exception("Faulty Stream")


async def websocket_endpoint(session: WebSocket) -> None:
    await session.accept()
    await session.send_text("Hello, world!")
    await session.close()


class CustomMiddleware(HTTPMiddleware):
    async def dispatch(self, conn: HTTPConnection) -> AsyncGenerator[None, Response]:
        response = yield
        response.headers["Custom-Header"] = "Example"


app = Starlette(
    routes=[
        Route("/", endpoint=homepage),
        Route("/exc", endpoint=exc),
        Route("/exc-stream", endpoint=exc_stream),
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

    with client.websocket_connect("/ws") as session:
        text = session.receive_text()
        assert text == "Hello, world!"


def test_state_data_across_multiple_middlewares(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    async def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    expected_value1 = "foo"
    expected_value2 = "bar"

    async def middleware_a(conn: HTTPConnection) -> AsyncGenerator[None, Response]:
        conn.state.foo = expected_value1
        yield

    async def middleware_b(conn: HTTPConnection) -> AsyncGenerator[None, Response]:
        conn.state.bar = expected_value2
        response = yield
        response.headers["X-State-Foo"] = conn.state.foo

    async def middleware_c(conn: HTTPConnection) -> AsyncGenerator[None, Response]:
        response = yield
        response.headers["X-State-Bar"] = conn.state.bar

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


def test_too_many_yields(test_client_factory: Callable[[ASGIApp], TestClient]) -> None:
    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[None, Response]:
            _ = yield
            yield

    app = Starlette(middleware=[Middleware(CustomMiddleware)])

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="should yield exactly once"):
        client.get("/")


def test_early_response(test_client_factory: Callable[[ASGIApp], TestClient]) -> None:
    async def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[Optional[Response], Response]:
            if conn.headers.get("X-Early") == "true":
                yield Response(status_code=401)
            else:
                yield None

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[Middleware(CustomMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "OK"
    response = client.get("/", headers={"X-Early": "true"})
    assert response.status_code == 401


def test_early_response_too_many_yields(
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

    async def failure(request: Request) -> Response:
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


def test_error_handling_must_send_response(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    class Failed(Exception):
        pass

    async def failure(request: Request) -> Response:
        raise Failed()

    class CustomMiddleware(HTTPMiddleware):
        async def dispatch(
            self, conn: HTTPConnection
        ) -> AsyncGenerator[None, Response]:
            try:
                yield
            except Failed:
                pass  # `yield <response>` expected

    app = Starlette(
        routes=[Route("/fail", failure)],
        middleware=[Middleware(CustomMiddleware)],
    )

    client = test_client_factory(app)
    with pytest.raises(RuntimeError, match="no response was returned"):
        client.get("/fail")


def test_no_dispatch_given(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    app = Starlette(middleware=[Middleware(HTTPMiddleware)])

    client = test_client_factory(app)
    with pytest.raises(NotImplementedError, match="No dispatch implementation"):
        client.get("/")


def test_response_stub_attributes(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    async def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    async def dispatch(conn: HTTPConnection) -> AsyncGenerator[None, Response]:
        response = yield
        if conn.url.path == "/status_code":
            assert response.status_code == 200
            response.status_code = 401
        if conn.url.path == "/media_type":
            assert response.media_type == "text/plain; charset=utf-8"
            response.media_type = "text/csv"
        if conn.url.path == "/body-get":
            response.body
        if conn.url.path == "/body-set":
            response.body = b"changed"

    app = Starlette(
        routes=[
            Route("/status_code", homepage),
            Route("/media_type", homepage),
            Route("/body-get", homepage),
            Route("/body-set", homepage),
        ],
        middleware=[Middleware(HTTPMiddleware, dispatch=dispatch)],
    )

    client = test_client_factory(app)

    with pytest.raises(
        RuntimeError, match="Setting .status_code in HTTPMiddleware is not supported."
    ):
        client.get("/status_code")

    with pytest.raises(
        RuntimeError, match="Setting .media_type in HTTPMiddleware is not supported"
    ):
        client.get("/media_type")

    with pytest.raises(
        RuntimeError,
        match="Accessing the response body in HTTPMiddleware is not supported",
    ):
        client.get("/body-get")

    with pytest.raises(
        RuntimeError,
        match="Setting the response body in HTTPMiddleware is not supported",
    ):
        client.get("/body-set")

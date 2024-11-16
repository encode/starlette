from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import ContentStream, PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from tests.types import TestClientFactory


def test_gzip_responses(test_client_factory: TestClientFactory) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("x" * 4000, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(GZipMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.text == "x" * 4000
    assert response.headers["Content-Encoding"] == "gzip"
    assert int(response.headers["Content-Length"]) < 4000


def test_gzip_not_in_accept_encoding(test_client_factory: TestClientFactory) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("x" * 4000, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(GZipMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": "identity"})
    assert response.status_code == 200
    assert response.text == "x" * 4000
    assert "Content-Encoding" not in response.headers
    assert int(response.headers["Content-Length"]) == 4000


def test_gzip_ignored_for_small_responses(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK", status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(GZipMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.text == "OK"
    assert "Content-Encoding" not in response.headers
    assert int(response.headers["Content-Length"]) == 2


def test_gzip_streaming_response(test_client_factory: TestClientFactory) -> None:
    class VerifyingMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            self.send = send
            self.received_chunks: list[bytes] = []
            await self.app(scope, receive, self.sent_from_gzip)
            assert all(chunk != b"" for chunk in self.received_chunks)
            assert len(self.received_chunks) == 11

        async def sent_from_gzip(self, message: Message) -> None:
            message_type = message["type"]
            if message_type == "http.response.body":
                body = message.get("body", b"")
                self.received_chunks.append(body)
            await self.send(message)

    def homepage(request: Request) -> StreamingResponse:
        async def generator(bytes: bytes, count: int) -> ContentStream:
            for index in range(count):
                yield bytes

        streaming = generator(bytes=b"x" * 400, count=10)
        return StreamingResponse(streaming, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[
            Middleware(VerifyingMiddleware),
            Middleware(GZipMiddleware),
        ],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.text == "x" * 4000
    assert response.headers["Content-Encoding"] == "gzip"
    assert "Content-Length" not in response.headers


def test_gzip_ignored_for_responses_with_encoding_set(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> StreamingResponse:
        async def generator(bytes: bytes, count: int) -> ContentStream:
            for index in range(count):
                yield bytes

        streaming = generator(bytes=b"x" * 400, count=10)
        return StreamingResponse(streaming, status_code=200, headers={"Content-Encoding": "text"})

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(GZipMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": "gzip, text"})
    assert response.status_code == 200
    assert response.text == "x" * 4000
    assert response.headers["Content-Encoding"] == "text"
    assert "Content-Length" not in response.headers

from typing import Callable

import zstandard

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.compress import (
    CompressMiddleware,
    deregister_compress_content_type,
    parse_accept_encoding,
    register_compress_content_type,
)
from starlette.requests import Request
from starlette.responses import (
    ContentStream,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp

TestClientFactory = Callable[[ASGIApp], TestClient]


def test_compress_responses(test_client_factory: TestClientFactory) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("x" * 4000, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200

        # httpx does not support zstd yet
        # https://github.com/encode/httpx/pull/3139
        if encoding == "zstd":
            response._text = zstandard.decompress(response.content).decode()

        assert response.text == "x" * 4000
        assert response.headers["Content-Encoding"] == encoding
        assert int(response.headers["Content-Length"]) < 4000


def test_compress_not_in_accept_encoding(
    test_client_factory: TestClientFactory
) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("x" * 4000, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": "identity"})
    assert response.status_code == 200
    assert response.text == "x" * 4000
    assert "Content-Encoding" not in response.headers
    assert int(response.headers["Content-Length"]) == 4000


def test_compress_ignored_for_small_responses(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK", status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200
        assert response.text == "OK"
        assert "Content-Encoding" not in response.headers
        assert int(response.headers["Content-Length"]) == 2


def test_compress_streaming_response(test_client_factory: TestClientFactory) -> None:
    def homepage(request: Request) -> StreamingResponse:
        async def generator(bytes: bytes, count: int) -> ContentStream:
            for _ in range(count):
                yield bytes

        streaming = generator(bytes=b"x" * 400, count=10)
        return StreamingResponse(streaming, status_code=200, media_type="text/plain")

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200

        # httpx does not support zstd yet
        # https://github.com/encode/httpx/pull/3139
        if encoding == "zstd":
            response._text = (
                zstandard.ZstdDecompressor()
                .decompressobj()
                .decompress(response.content)
                .decode()
            )

        assert response.text == "x" * 4000
        assert response.headers["Content-Encoding"] == encoding
        assert "Content-Length" not in response.headers


def test_compress_ignored_for_responses_with_encoding_set(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> StreamingResponse:
        async def generator(bytes: bytes, count: int) -> ContentStream:
            for _ in range(count):
                yield bytes

        streaming = generator(bytes=b"x" * 400, count=10)
        return StreamingResponse(
            streaming, status_code=200, headers={"Content-Encoding": "test"}
        )

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": f"{encoding}, test"})
        assert response.status_code == 200
        assert response.text == "x" * 4000
        assert response.headers["Content-Encoding"] == "test"
        assert "Content-Length" not in response.headers


def test_compress_ignored_for_missing_accept_encoding(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("x" * 4000, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/", headers={"accept-encoding": ""})
    assert response.status_code == 200
    assert response.text == "x" * 4000
    assert "Content-Encoding" not in response.headers
    assert int(response.headers["Content-Length"]) == 4000


def test_compress_ignored_for_missing_content_type(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return Response("x" * 4000, status_code=200, media_type=None)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200
        assert response.text == "x" * 4000
        assert "Content-Encoding" not in response.headers
        assert int(response.headers["Content-Length"]) == 4000


def test_compress_registered_content_type(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return Response("x" * 4000, status_code=200, media_type="test/test")

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CompressMiddleware)],
    )

    client = test_client_factory(app)

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200
        assert "Content-Encoding" not in response.headers
        assert int(response.headers["Content-Length"]) == 4000

    register_compress_content_type("test/test")

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200
        assert response.headers["Content-Encoding"] == encoding
        assert int(response.headers["Content-Length"]) < 4000

    deregister_compress_content_type("test/test")

    for encoding in ("gzip", "br", "zstd"):
        response = client.get("/", headers={"accept-encoding": encoding})
        assert response.status_code == 200
        assert "Content-Encoding" not in response.headers
        assert int(response.headers["Content-Length"]) == 4000


def test_parse_accept_encoding():
    assert parse_accept_encoding("") == frozenset()
    assert parse_accept_encoding("gzip, deflate") == {"gzip", "deflate"}
    assert parse_accept_encoding("br;q=1.0,gzip;q=0.8, *;q=0.1") == {"br", "gzip"}

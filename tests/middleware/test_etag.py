from typing import Callable

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.etag import ETagMiddleware
from starlette.requests import Request
from starlette.responses import (
    ContentStream,
    FileResponse,
    PlainTextResponse,
    StreamingResponse,
)
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp

TestClientFactory = Callable[[ASGIApp], TestClient]


def test_etag_responses(test_client_factory: TestClientFactory) -> None:
    data = "x" * 4000

    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse(data, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(ETagMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == data
    etag = response.headers["ETag"]
    assert etag

    response = client.get("/", headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["ETag"] == etag


def test_etag_ignored_for_small_responses(test_client_factory: TestClientFactory) -> None:
    data = "x" * 40

    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse(data, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(ETagMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == data
    assert response.headers.get("ETag") is None


def test_etag_ignored_for_non_200_responses(test_client_factory: TestClientFactory) -> None:
    data = "x" * 4000

    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse(data, status_code=500)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(ETagMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 500
    assert response.text == data
    assert response.headers.get("ETag") is None


def test_etag_ignored_for_streamming_responses(test_client_factory: TestClientFactory) -> None:
    data = b"x" * 40

    def homepage(request: Request) -> StreamingResponse:
        count = int(request.query_params["count"])

        async def generator(bytes: bytes, count: int) -> ContentStream:
            for _ in range(count):
                yield bytes

        streaming = generator(bytes=data, count=count)
        return StreamingResponse(streaming, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(ETagMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/?count=1")
    assert response.status_code == 200
    assert response.content == data
    assert response.headers.get("ETag") is None

    client = test_client_factory(app)
    response = client.get("/?count=2")
    assert response.status_code == 200
    assert response.content == data * 2
    assert response.headers.get("ETag") is None


def test_etag_for_file_responses(
    test_client_factory: TestClientFactory,
) -> None:
    def homepage(request: Request) -> FileResponse:
        return FileResponse(__file__)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(ETagMiddleware)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    etag = response.headers["ETag"]
    assert etag

    response = client.get("/", headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["ETag"] == etag

    chunk_size = FileResponse.chunk_size
    try:
        FileResponse.chunk_size = 64  # set it to a smaller size for testing chunked body
        response = client.get("/", headers={"If-None-Match": etag})
        assert response.status_code == 304
        etag2 = response.headers["ETag"]
        assert etag == etag2
    finally:
        FileResponse.chunk_size = chunk_size  # reset chunk_size

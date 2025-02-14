import gc
import gzip
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from typing import TYPE_CHECKING, Callable
from unittest.mock import AsyncMock, Mock

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from starlette.requests import Request
from starlette.responses import ContentStream, PlainTextResponse, StreamingResponse
from starlette.routing import Route
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
    def homepage(request: Request) -> StreamingResponse:
        async def generator(bytes: bytes, count: int) -> ContentStream:
            for index in range(count):
                yield bytes

        streaming = generator(bytes=b"x" * 400, count=10)
        return StreamingResponse(streaming, status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(GZipMiddleware)],
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


if TYPE_CHECKING:
    from sys import UnraisableHookArgs
else:
    UnraisableHookArgs = object


@contextmanager
def override_custom_unraisable_exception_hook_and_gc_collect(
    unraisable_hook: Callable[[UnraisableHookArgs], None],
) -> Iterator[None]:
    unraisable_hook_before_test = sys.unraisablehook
    sys.unraisablehook = unraisable_hook
    try:
        yield
        gc.collect()
    finally:
        sys.unraisablehook = unraisable_hook_before_test


# https://github.com/python/cpython/blob/247b50dec8af47ed8a80069117e07b7139f9d54f/Doc/whatsnew/3.13.rst#io
@pytest.mark.skipif(sys.version_info < (3, 13), reason="requires python3.13 or higher")
def test_gzip_responder_not_writes_not_raised_exception_warning(
    test_client_factory: TestClientFactory,
) -> None:
    # check unraisablehook trgiggers when BytesIO destroyed before GzipFile
    mock_for_test_bytesio_and_gzip_unraisable = Mock()
    with override_custom_unraisable_exception_hook_and_gc_collect(
        unraisable_hook=mock_for_test_bytesio_and_gzip_unraisable
    ):
        b = BytesIO()
        g = gzip.GzipFile(fileobj=b, mode="wb")
        del b
        del g

    assert mock_for_test_bytesio_and_gzip_unraisable.called

    mock_for_test_gzip_responder_unraisable = Mock()
    with override_custom_unraisable_exception_hook_and_gc_collect(
        unraisable_hook=mock_for_test_gzip_responder_unraisable
    ):
        responder = GZipResponder(app=AsyncMock(), minimum_size=500)
        del responder

    assert not mock_for_test_gzip_responder_unraisable.called

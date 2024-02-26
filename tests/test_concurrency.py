from contextvars import ContextVar
from typing import Callable, Iterator

import pytest

from starlette.applications import Starlette
from starlette.concurrency import iterate_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

TestClientFactory = Callable[..., TestClient]


def test_accessing_context_from_threaded_sync_endpoint(
    test_client_factory: TestClientFactory,
) -> None:
    ctxvar: ContextVar[bytes] = ContextVar("ctxvar")
    ctxvar.set(b"data")

    def endpoint(request: Request) -> Response:
        return Response(ctxvar.get())

    app = Starlette(routes=[Route("/", endpoint)])
    client = test_client_factory(app)

    resp = client.get("/")
    assert resp.content == b"data"


@pytest.mark.anyio
async def test_iterate_in_threadpool() -> None:
    class CustomIterable:
        def __iter__(self) -> Iterator[int]:
            yield from range(3)

    assert [v async for v in iterate_in_threadpool(CustomIterable())] == [0, 1, 2]

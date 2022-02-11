import contextvars

import anyio
import pytest

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool, run_until_first_complete
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


@pytest.mark.anyio
async def test_run_until_first_complete():
    task1_finished = anyio.Event()
    task2_finished = anyio.Event()

    async def task1():
        task1_finished.set()

    async def task2():
        await task1_finished.wait()
        await anyio.sleep(0)  # pragma: nocover
        task2_finished.set()  # pragma: nocover

    await run_until_first_complete((task1, {}), (task2, {}))
    assert task1_finished.is_set()
    assert not task2_finished.is_set()


def test_accessing_context_from_threaded_sync_endpoint(test_client_factory) -> None:
    ctxvar: contextvars.ContextVar[bytes] = contextvars.ContextVar("ctxvar")
    ctxvar.set(b"data")

    def endpoint(request: Request) -> Response:
        return Response(ctxvar.get())

    app = Starlette(routes=[Route("/", endpoint)])
    client = test_client_factory(app)

    resp = client.get("/")
    assert resp.content == b"data"


@pytest.mark.anyio
async def test_restore_context_from_thread_previously_set():
    """Value outside of threadpool is overwitten with value set in threadpool"""
    ctxvar = contextvars.ContextVar("ctxvar")
    ctxvar.set("spam")

    def sync_task():
        ctxvar.set("ham")

    await run_in_threadpool(sync_task)
    assert ctxvar.get() == "ham"


@pytest.mark.anyio
async def test_restore_context_from_thread_previously_unset():
    """Value outside of threadpool is set to value in threadpool"""
    ctxvar = contextvars.ContextVar("ctxvar")

    def sync_task():
        ctxvar.set("ham")

    await run_in_threadpool(sync_task)
    assert ctxvar.get() == "ham"


@pytest.mark.anyio
async def test_restore_context_from_thread_new_cvar():
    """Value outside of threadpool is set for a cvar created in the threadpool"""
    ctxvar = None

    def sync_task():
        nonlocal ctxvar
        ctxvar = contextvars.ContextVar("ctxvar")
        ctxvar.set("ham")

    await run_in_threadpool(sync_task)
    assert ctxvar.get() == "ham"

import contextvars

import anyio
import pytest

from starlette.concurrency import run_in_threadpool, run_until_first_complete


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


@pytest.mark.anyio
async def test_restore_context_from_thread():
    ctxvar = contextvars.ContextVar("ctxvar", default="spam")

    def sync_task():
        ctxvar.set("ham")
    
    await run_in_threadpool(sync_task)
    assert ctxvar.get() == "ham"

from typing import Any, AsyncIterable, Callable, List

import pytest

from starlette.background import BackgroundTask, BackgroundTasks
from starlette.middleware.background import BackgroundTaskMiddleware
from starlette.responses import Response, StreamingResponse
from starlette.testclient import TestClient
from starlette.types import ASGIApp

TestClientFactory = Callable[[ASGIApp], TestClient]


@pytest.fixture(
    params=[[], [BackgroundTaskMiddleware]],
    ids=["without BackgroundTaskMiddleware", "with BackgroundTaskMiddleware"],
)
def test_client_factory_mw(
    test_client_factory: TestClientFactory, request: Any
) -> TestClientFactory:
    mw_stack: List[Callable[[ASGIApp], ASGIApp]] = request.param

    def client_factory(app: ASGIApp) -> TestClient:
        for mw in mw_stack:
            app = mw(app)
        return test_client_factory(app)

    return client_factory


async def stream() -> AsyncIterable[bytes]:
    yield b"task initiated"


response_factories: List[Callable[[BackgroundTask], Response]] = [
    lambda background: StreamingResponse(
        stream(), media_type="text/plain", background=background
    ),
    lambda background: Response(
        "task initiated", media_type="text/plain", background=background
    ),
]
response_ids = ["StreamingResponse", "Response"]


@pytest.mark.parametrize("response_factory", response_factories, ids=response_ids)
def test_async_task(
    test_client_factory_mw: TestClientFactory,
    response_factory: Callable[[BackgroundTask], Response],
):
    TASK_COMPLETE = False

    async def async_task():
        nonlocal TASK_COMPLETE
        TASK_COMPLETE = True

    task = BackgroundTask(async_task)

    async def app(scope, receive, send):
        response = response_factory(task)
        await response(scope, receive, send)

    client = test_client_factory_mw(app)
    response = client.get("/")
    assert response.text == "task initiated"
    assert TASK_COMPLETE


def test_sync_task(test_client_factory_mw: TestClientFactory):
    TASK_COMPLETE = False

    def sync_task():
        nonlocal TASK_COMPLETE
        TASK_COMPLETE = True

    task = BackgroundTask(sync_task)

    async def app(scope, receive, send):
        response = Response("task initiated", media_type="text/plain", background=task)
        await response(scope, receive, send)

    client = test_client_factory_mw(app)
    response = client.get("/")
    assert response.text == "task initiated"
    assert TASK_COMPLETE


def test_multiple_tasks(test_client_factory_mw: TestClientFactory):
    TASK_COUNTER = 0

    def increment(amount):
        nonlocal TASK_COUNTER
        TASK_COUNTER += amount

    async def app(scope, receive, send):
        tasks = BackgroundTasks()
        tasks.add_task(increment, amount=1)
        tasks.add_task(increment, amount=2)
        tasks.add_task(increment, amount=3)
        response = Response(
            "tasks initiated", media_type="text/plain", background=tasks
        )
        await response(scope, receive, send)

    client = test_client_factory_mw(app)
    response = client.get("/")
    assert response.text == "tasks initiated"
    assert TASK_COUNTER == 1 + 2 + 3


def test_multi_tasks_failure_avoids_next_execution(
    test_client_factory_mw: TestClientFactory,
) -> None:
    TASK_COUNTER = 0

    def increment():
        nonlocal TASK_COUNTER
        TASK_COUNTER += 1
        if TASK_COUNTER == 1:
            raise Exception("task failed")

    async def app(scope, receive, send):
        tasks = BackgroundTasks()
        tasks.add_task(increment)
        tasks.add_task(increment)
        response = Response(
            "tasks initiated", media_type="text/plain", background=tasks
        )
        await response(scope, receive, send)

    client = test_client_factory_mw(app)
    with pytest.raises(Exception):
        client.get("/")
    assert TASK_COUNTER == 1

from tempfile import NamedTemporaryFile
from typing import Any, AsyncIterable, Callable, List

import pytest

from starlette.background import BackgroundTask, BackgroundTasks
from starlette.middleware.background import BackgroundTaskMiddleware
from starlette.responses import FileResponse, Response, StreamingResponse
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

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


def response_app_factory(task: BackgroundTask) -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send):
        response = Response(b"task initiated", media_type="text/plain", background=task)
        await response(scope, receive, send)

    return app


def file_response_app_factory(task: BackgroundTask) -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send):
        with NamedTemporaryFile("wb+") as f:
            f.write(b"task initiated")
            f.seek(0)
            response = FileResponse(f.name, media_type="text/plain", background=task)
            await response(scope, receive, send)

    return app


def streaming_response_app_factory(task: BackgroundTask) -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send):
        async def stream() -> AsyncIterable[bytes]:
            yield b"task initiated"

        response = StreamingResponse(stream(), media_type="text/plain", background=task)
        await response(scope, receive, send)

    return app


@pytest.mark.parametrize(
    "app_factory",
    [
        response_app_factory,
        streaming_response_app_factory,
        file_response_app_factory,
    ],
)
def test_async_task(
    test_client_factory_mw: TestClientFactory,
    app_factory: Callable[[BackgroundTask], ASGIApp],
):
    TASK_COMPLETE = False

    async def async_task():
        nonlocal TASK_COMPLETE
        TASK_COMPLETE = True

    task = BackgroundTask(async_task)

    app = app_factory(task)

    client = test_client_factory_mw(app)
    response = client.get("/")
    assert response.text == "task initiated"
    assert TASK_COMPLETE


def test_sync_task(test_client_factory: TestClientFactory):
    TASK_COMPLETE = False

    def sync_task():
        nonlocal TASK_COMPLETE
        TASK_COMPLETE = True

    task = BackgroundTask(sync_task)

    async def app(scope, receive, send):
        response = Response("task initiated", media_type="text/plain", background=task)
        await response(scope, receive, send)

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "task initiated"
    assert TASK_COMPLETE


def test_multiple_tasks(test_client_factory: TestClientFactory):
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

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "tasks initiated"
    assert TASK_COUNTER == 1 + 2 + 3


def test_multi_tasks_failure_avoids_next_execution(
    test_client_factory: TestClientFactory,
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

    client = test_client_factory(app)
    with pytest.raises(Exception):
        client.get("/")
    assert TASK_COUNTER == 1

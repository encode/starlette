from starlette.responses import Response
from starlette.tasks import BackgroundTask
from starlette.testclient import TestClient
import asyncio

def test_async_task():
    async def async_task():
        count = 0
        for num in range(3):
            count+= 1
            await asyncio.sleep(1)
        return count

    task = BackgroundTask(async_task)
    def app(scope):
        async def asgi(receive, send):
            response = Response(
                "task initiated",
                media_type="text/plain",
                background=task
            )
            await response(receive, send)
        return asgi

    client = TestClient(app)
    assert task.result == None
    response = client.get("/")
    assert len(task.id) > 0
    assert response.text == "task initiated"
    assert task.result == 3

def test_sync_task():
    def sync_task():
        num = 500
        count = 0
        while count != num:
            count += 1
        return count

    task = BackgroundTask(sync_task)
    def app(scope):
        async def asgi(receive, send):
            response = Response(
                "task initiated",
                media_type="text/plain",
                background=task
            )
            await response(receive, send)
        return asgi

    client = TestClient(app)
    assert task.result == None
    response = client.get("/")
    assert len(task.id) > 0
    assert response.text == "task initiated"
    assert task.result == 500
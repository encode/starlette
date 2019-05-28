import asyncio
import pytest

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

mock_service = Starlette()


@mock_service.route("/")
def mock_service_endpoint(request):
    return JSONResponse({"mock": "example"})


@mock_service.websocket_route("/ws")
async def mock_service_websocket_endpoint(websocket):
    await websocket.accept()
    await websocket.send_json({"message": "test"})
    await websocket.close()


app = Starlette()


@app.route("/")
def homepage(request):
    client = TestClient(mock_service)
    response = client.get("/")
    return JSONResponse(response.json())


@app.websocket_route("/ws")
async def websocket_endpoint(websocket):
    await websocket.accept()
    with TestClient(mock_service).websocket_connect("/ws") as mock_service_ws:
        await websocket.send_json(mock_service_ws.receive_json())
    await websocket.close()


startup_error_app = Starlette()


@startup_error_app.on_event("startup")
def startup():
    raise RuntimeError()


def test_use_testclient_in_endpoint():
    """
    We should be able to use the test client within applications.

    This is useful if we need to mock out other services,
    during tests or in development.
    """
    client = TestClient(app)
    response = client.get("/")
    assert response.json() == {"mock": "example"}


def testclient_as_contextmanager():
    with TestClient(app):
        pass


def test_error_on_startup():
    with pytest.raises(RuntimeError):
        with TestClient(startup_error_app):
            pass  # pragma: no cover


def test_testclient_asgi2():
    def app(scope):
        async def inner(receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"text/plain"]],
                }
            )
            await send({"type": "http.response.body", "body": b"Hello, world!"})

        return inner

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "Hello, world!"


def test_testclient_asgi3():
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"Hello, world!"})

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "Hello, world!"


def test_websocket_blocking_receive():
    def app(scope):
        async def respond(websocket):
            await websocket.send_json({"message": "test"})

        async def asgi(receive, send):
            websocket = WebSocket(scope, receive=receive, send=send)
            await websocket.accept()
            asyncio.ensure_future(respond(websocket))
            try:
                # this will block as the client does not send us data
                # it should not prevent `respond` from executing though
                await websocket.receive_json()
            except WebSocketDisconnect:
                pass

        return asgi

    client = TestClient(app)
    with client.websocket_connect("/") as websocket:
        data = websocket.receive_json()
        assert data == {"message": "test"}


def test_use_websocket_connect_in_endpoint():
    with TestClient(app).websocket_connect("/ws") as _ws:
        assert _ws.receive_json() == {"message": "test"}


def test_websocket_connect_runs_in_current_event_loop():
    app = Starlette()

    @app.on_event("startup")
    async def open_connection_pool():
        app.pool = asyncio.ensure_future(asyncio.sleep(0.1))

    @app.websocket_route("/")
    async def websocket_endpoint(websocket):
        await websocket.accept()
        await app.pool
        await websocket.send_json({"message": "test"})
        await websocket.close()

    with TestClient(app) as client, client.websocket_connect("/") as websocket:
        data = websocket.receive_json()
        assert data == {"message": "test"}

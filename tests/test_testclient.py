import asyncio
import time

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

mock_service = Starlette()


@mock_service.route("/")
def mock_service_endpoint(request):
    return JSONResponse({"mock": "example"})


@mock_service.route("/slow_response")
def slow_response(request):
    time.sleep(0.01)
    return JSONResponse({"mock": "slow example"})


@mock_service.route("/async_slow_response")
async def async_slow_response(request):
    # time.sleep(0.01)
    await asyncio.sleep(0.01)
    return JSONResponse({"mock": "slow example"})


app = Starlette()


@app.route("/")
def homepage(request):
    client = TestClient(mock_service)
    response = client.get("/")
    return JSONResponse(response.json())


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


def test_use_testclient_as_contextmanager():
    with TestClient(app):
        pass


def test_error_on_startup():
    with pytest.raises(RuntimeError):
        with TestClient(startup_error_app):
            pass  # pragma: no cover


def test_exception_in_middleware():
    class MiddlewareException(Exception):
        pass

    class BrokenMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            raise MiddlewareException()

    broken_middleware = Starlette(middleware=[Middleware(BrokenMiddleware)])

    with pytest.raises(MiddlewareException):
        with TestClient(broken_middleware):
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


@pytest.mark.parametrize("endpoint", ["/slow_response", "/async_slow_response"])
def test_timeout(endpoint):
    client = TestClient(mock_service, raise_server_exceptions=True)

    with pytest.raises(ValueError):
        client.get("/slow_response", timeout=(1, 1))

    with pytest.raises(asyncio.TimeoutError):
        client.get(endpoint, timeout=0.001)

    response = client.get(endpoint, timeout=1)
    assert response.json() == {"mock": "slow example"}

    response = client.get(endpoint)
    assert response.json() == {"mock": "slow example"}

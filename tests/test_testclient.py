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


@pytest.mark.parametrize("raise_server_exceptions", (True, False))
def test_error_with_middleware_and_testclient_exit(raise_server_exceptions):
    """TestClient's __exit__ should not raise the exception again."""
    app = Starlette()

    events = []

    @app.on_event("startup")
    async def startup():
        events.append("startup")

    @app.on_event("shutdown")
    async def shutdown():
        events.append("shutdown")

    @app.middleware("http")
    async def http_middleware(request, call_next):
        return await call_next(request)

    @app.middleware("http")
    async def second_middleware(request, call_next):
        return await call_next(request)

    if raise_server_exceptions:

        @app.route("/error")
        async def error(request):
            pytest.fail("should_only_fail_once")

        with TestClient(app, raise_server_exceptions=True) as client:
            with pytest.raises(pytest.fail.Exception):
                client.get("/error")
    else:

        @app.route("/error")
        async def error(request):
            pytest.fail("should_not_raise")

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/error")
            assert response.status_code == 500

    assert events == ["startup", "shutdown"]

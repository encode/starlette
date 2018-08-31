from starlette.exceptions import ExceptionMiddleware, HTTPException
from starlette.response import PlainTextResponse
from starlette.routing import Router, Path
from starlette.testclient import TestClient
import pytest


def raise_runtime_error(scope):
    async def asgi(receive, send):
        raise RuntimeError("Yikes")

    return asgi


def raise_http_exception(scope):
    async def asgi(receive, send):
        raise HTTPException(406)

    return asgi


app = Router(
    routes=[
        Path("/runtime_error", app=raise_runtime_error),
        Path("/not_acceptable", app=raise_http_exception),
    ]
)


app = ExceptionMiddleware(app)
client = TestClient(app, raise_exceptions=False)


def test_server_error():
    response = client.get("/runtime_error")
    assert response.status_code == 500
    assert response.text == "Server Error"


def test_not_acceptable():
    response = client.get("/not_acceptable")
    assert response.status_code == 406
    assert response.text == "Not Acceptable"


def test_websockets_should_raise():
    with pytest.raises(RuntimeError):
        client.websocket_connect("/runtime_error")

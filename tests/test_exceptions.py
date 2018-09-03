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


def handled_exc_after_response(scope):
    async def asgi(receive, send):
        response = PlainTextResponse("OK", status_code=200)
        await response(receive, send)
        raise HTTPException(406)

    return asgi


app = Router(
    routes=[
        Path("/runtime_error", app=raise_runtime_error),
        Path("/not_acceptable", app=raise_http_exception),
        Path("/handled_exc_after_response", app=handled_exc_after_response),
    ]
)


app = ExceptionMiddleware(app)
client = TestClient(app)


def test_server_error():
    with pytest.raises(RuntimeError):
        response = client.get("/runtime_error")

    allow_500_client = TestClient(app, raise_exceptions=False)
    response = allow_500_client.get("/runtime_error")
    assert response.status_code == 500
    assert response.text == "Server Error"


def test_not_acceptable():
    response = client.get("/not_acceptable")
    assert response.status_code == 406
    assert response.text == "Not Acceptable"


def test_websockets_should_raise():
    with pytest.raises(RuntimeError):
        client.websocket_connect("/runtime_error")


def test_handled_exc_after_response():
    with pytest.raises(RuntimeError):
        client.get("/handled_exc_after_response")

    allow_200_client = TestClient(app, raise_exceptions=False)
    response = allow_200_client.get("/handled_exc_after_response")
    assert response.status_code == 200
    assert response.text == "OK"

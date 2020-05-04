import pytest

from starlette.exceptions import ExceptionMiddleware, HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route, Router, WebSocketRoute
from starlette.testclient import TestClient


def raise_runtime_error(request):
    raise RuntimeError("Yikes")


def not_acceptable(request):
    raise HTTPException(status_code=406)


def not_modified(request):
    raise HTTPException(status_code=304)


def sad_server(request):
    if request.headers.get("except") == "503":
        raise HTTPException(status_code=503)
    raise HTTPException(status_code=504)


class CustomRequest(Request):
    pass


class BadCustomRequest:
    pass


def fine_exception_handler(request: CustomRequest, exc):
    return PlainTextResponse(request.__class__.__name__, status_code=exc.status_code)


def bad_exception_handler(request: BadCustomRequest, exc):  # pragma: no cover
    return PlainTextResponse(request.__class__.__name__, status_code=exc.status_code)


class HandledExcAfterResponse:
    async def __call__(self, scope, receive, send):
        response = PlainTextResponse("OK", status_code=200)
        await response(scope, receive, send)
        raise HTTPException(status_code=406)


router = Router(
    routes=[
        Route("/runtime_error", endpoint=raise_runtime_error),
        Route("/not_acceptable", endpoint=not_acceptable),
        Route("/not_modified", endpoint=not_modified),
        Route("/handled_exc_after_response", endpoint=HandledExcAfterResponse()),
        Route("/sad_server", endpoint=sad_server),
        WebSocketRoute("/runtime_error", endpoint=raise_runtime_error),
    ]
)


app = ExceptionMiddleware(
    router, handlers={503: fine_exception_handler, 504: bad_exception_handler}
)
client = TestClient(app)


def test_not_acceptable():
    response = client.get("/not_acceptable")
    assert response.status_code == 406
    assert response.text == "Not Acceptable"


def test_not_modified():
    response = client.get("/not_modified")
    assert response.status_code == 304
    assert response.text == ""


def test_websockets_should_raise():
    with pytest.raises(RuntimeError):
        client.websocket_connect("/runtime_error")


def test_handled_exc_after_response():
    # A 406 HttpException is raised *after* the response has already been sent.
    # The exception middleware should raise a RuntimeError.
    with pytest.raises(RuntimeError):
        client.get("/handled_exc_after_response")

    # If `raise_server_exceptions=False` then the test client will still allow
    # us to see the response as it will have been seen by the client.
    allow_200_client = TestClient(app, raise_server_exceptions=False)
    response = allow_200_client.get("/handled_exc_after_response")
    assert response.status_code == 200
    assert response.text == "OK"


def test_force_500_response():
    def app(scope):
        raise RuntimeError()

    force_500_client = TestClient(app, raise_server_exceptions=False)
    response = force_500_client.get("/")
    assert response.status_code == 500
    assert response.text == ""


def test_repr():
    assert repr(HTTPException(404)) == (
        "HTTPException(status_code=404, detail='Not Found')"
    )
    assert repr(HTTPException(404, detail="Not Found: foo")) == (
        "HTTPException(status_code=404, detail='Not Found: foo')"
    )

    class CustomHTTPException(HTTPException):
        pass

    assert repr(CustomHTTPException(500, detail="Something custom")) == (
        "CustomHTTPException(status_code=500, detail='Something custom')"
    )


def test_sad_server_custom_req():
    response = client.get("/sad_server", headers={"except": "503"})
    assert response.status_code == 503
    assert response.text == "CustomRequest"


def test_sad_server_custom_req_fail():
    with pytest.raises(TypeError):
        client.get("/sad_server")

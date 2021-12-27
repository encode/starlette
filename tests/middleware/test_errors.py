import inspect
from unittest import mock

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.errors import (
    ServerErrorMiddleware,
    format_qual_name,
    get_symbol,
)
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount


def test_handler(test_client_factory):
    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    def error_500(request, exc):
        return JSONResponse({"detail": "Server Error"}, status_code=500)

    app = ServerErrorMiddleware(app, handler=error_500)
    client = test_client_factory(app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 500
    assert response.json() == {"detail": "Server Error"}


def test_debug_text(test_client_factory):
    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app, debug=True)
    client = test_client_factory(app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert "RuntimeError: Something went wrong" in response.text


def test_debug_html(test_client_factory):
    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app, debug=True)
    client = test_client_factory(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text


def test_debug_with_session_html(test_client_factory):
    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(SessionMiddleware(app, secret_key="key!"), debug=True)
    client = test_client_factory(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text
    assert "<summary>Session</summary>" in response.text


def test_debug_with_vendor_frames_html(test_client_factory):
    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(SessionMiddleware(app, secret_key="key!"), debug=True)
    client = test_client_factory(app, raise_server_exceptions=False)
    with mock.patch("starlette.middleware.errors.is_vendor", lambda f: True):
        response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text
    assert " vendor" in response.text  # css class added


def test_debug_masks_secrets(test_client_factory, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret!")

    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app, debug=True)
    client = test_client_factory(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text
    assert "********" in response.text


class ExampleClass:  # pragma: nocover
    def from_method(self):
        raise RuntimeError()

    @classmethod
    def from_classmethod(cls):
        raise RuntimeError()


def test_debug_with_app_state_html(test_client_factory):
    async def _app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = Starlette(
        debug=True,
        middleware=[Middleware(ServerErrorMiddleware, debug=True)],
        routes=[Mount("/", _app)],
    )
    client = test_client_factory(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text


def test_debug_after_response_sent(test_client_factory):
    async def app(scope, receive, send):
        response = Response(b"", status_code=204)
        await response(scope, receive, send)
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app, debug=True)
    client = test_client_factory(app)
    with pytest.raises(RuntimeError):
        client.get("/")


def test_debug_not_http(test_client_factory):
    """
    DebugMiddleware should just pass through any non-http messages as-is.
    """

    async def app(scope, receive, send):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app)

    with pytest.raises(RuntimeError):
        client = test_client_factory(app)
        with client.websocket_connect("/"):
            pass  # pragma: nocover


def test_format_qual_name():
    class Example:  # pragma: nocover
        @classmethod
        def method(cls):
            pass

    assert format_qual_name(Example) == "tests.middleware.test_errors.Example"
    assert format_qual_name(Example()) == "tests.middleware.test_errors.Example"


def test_get_symbol():
    try:
        instance = ExampleClass()
        instance.from_method()
    except RuntimeError as ex:
        frames = inspect.getinnerframes(ex.__traceback__, 2)
        assert get_symbol(frames[-1]) == "ExampleClass.from_method"


def test_get_symbol_class_method():
    try:
        ExampleClass.from_classmethod()
    except RuntimeError as ex:
        frames = inspect.getinnerframes(ex.__traceback__, 2)
        assert get_symbol(frames[-1]) == "ExampleClass.from_classmethod"

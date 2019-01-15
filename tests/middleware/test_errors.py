import pytest

from starlette.middleware.errors import DebugGenerator, ServerErrorMiddleware
from starlette.responses import JSONResponse, Response
from starlette.testclient import TestClient


def test_handler():
    def app(scope):
        async def asgi(receive, send):
            raise RuntimeError("Something went wrong")

        return asgi

    def error_500(request, exc):
        return JSONResponse({"detail": "Server Error"}, status_code=500)

    app = ServerErrorMiddleware(app, handler=error_500)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 500
    assert response.json() == {"detail": "Server Error"}


def test_debug_text():
    def app(scope):
        async def asgi(receive, send):
            raise RuntimeError("Something went wrong")

        return asgi

    app = ServerErrorMiddleware(app, debug=True)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert "RuntimeError" in response.text


def test_debug_html():
    def app(scope):
        async def asgi(receive, send):
            raise RuntimeError("Something went wrong")

        return asgi

    app = ServerErrorMiddleware(app, debug=True)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text


def test_debug_after_response_sent():
    def app(scope):
        async def asgi(receive, send):
            response = Response(b"", status_code=204)
            await response(receive, send)
            raise RuntimeError("Something went wrong")

        return asgi

    app = ServerErrorMiddleware(app, debug=True)
    client = TestClient(app)
    with pytest.raises(RuntimeError):
        client.get("/")


def test_debug_error_during_scope():
    def app(scope):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app, debug=True)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Accept": "text/html, */*"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/html")
    assert "RuntimeError" in response.text


def test_debug_not_http():
    """
    DebugMiddleware should just pass through any non-http messages as-is.
    """

    def app(scope):
        raise RuntimeError("Something went wrong")

    app = ServerErrorMiddleware(app)

    with pytest.raises(RuntimeError):
        app({"type": "websocket"})


def test_customized_debug_generator():
    exc = RuntimeError("Something went wrong")

    class CustomDebugGenerator(DebugGenerator):
        title = "My debugger"
        styles = "p{color: red;}"

    gen = CustomDebugGenerator(exc)
    html = gen.generate_html()
    assert "p{color: red;}" in html
    assert "Something went wrong" in html
    assert "My debugger" in html

import os
from typing import Callable

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from starlette.testclient import TestClient
from starlette.types import ASGIApp


def test_templates(tmpdir, test_client_factory):
    path = os.path.join(tmpdir, "index.html")
    with open(path, "w") as file:
        file.write("<html>Hello, <a href='{{ url_for('homepage') }}'>world</a></html>")

    async def homepage(request):
        return templates.TemplateResponse("index.html", {"request": request})

    app = Starlette(
        debug=True,
        routes=[Route("/", endpoint=homepage)],
    )
    templates = Jinja2Templates(directory=str(tmpdir))

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "<html>Hello, <a href='http://testserver/'>world</a></html>"
    assert response.template.name == "index.html"
    assert set(response.context.keys()) == {"request"}


def test_template_response_requires_request(tmpdir):
    templates = Jinja2Templates(str(tmpdir))
    with pytest.raises(ValueError):
        templates.TemplateResponse("", {})


def test_templates_extension_response_replaced(
    tmpdir: str, test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    # if a middleware replaces the response
    # we do not send the template debug/test info

    path = os.path.join(tmpdir, "index.html")
    with open(path, "w") as file:
        file.write("<html>Hello, <a href='{{ url_for('homepage') }}'>world</a></html>")

    templates = Jinja2Templates(directory=str(tmpdir))

    async def homepage(request: Request) -> Response:
        return templates.TemplateResponse("index.html", {"request": request})

    class MiddlewareReplacesResponse(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return HTMLResponse("<html>Bye!</html>")

    app = Starlette(
        debug=True,
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(MiddlewareReplacesResponse)],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "<html>Bye!</html>"
    assert not hasattr(response, "template")
    assert not hasattr(response, "request")

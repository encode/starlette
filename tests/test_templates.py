import os
from pathlib import Path

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Route
from starlette.templating import Jinja2Templates


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


def test_calls_context_processors(tmp_path, test_client_factory):
    path: Path = tmp_path / "index.html"
    path.write_text("<html>Hello {{ username }}</html>")

    async def homepage(request):
        return templates.TemplateResponse("index.html", {"request": request})

    def hello_world_processor(request):
        return {"username": "World"}

    app = Starlette(
        debug=True,
        routes=[Route("/", endpoint=homepage)],
    )
    templates = Jinja2Templates(
        directory=tmp_path,
        context_processors=[
            hello_world_processor,
        ],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "<html>Hello World</html>"
    assert response.template.name == "index.html"
    assert set(response.context.keys()) == {"request", "username"}


def test_template_with_middleware(tmpdir, test_client_factory):
    path = os.path.join(tmpdir, "index.html")
    with open(path, "w") as file:
        file.write("<html>Hello, <a href='{{ url_for('homepage') }}'>world</a></html>")

    async def homepage(request):
        return templates.TemplateResponse("index.html", {"request": request})

    class CustomMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return await call_next(request)

    app = Starlette(
        debug=True,
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(CustomMiddleware)],
    )
    templates = Jinja2Templates(directory=str(tmpdir))

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "<html>Hello, <a href='http://testserver/'>world</a></html>"
    assert response.template.name == "index.html"
    assert set(response.context.keys()) == {"request"}


def test_templates_with_directories(tmp_path, test_client_factory):
    dir_home: Path = tmp_path.resolve() / "home"
    dir_home.mkdir()
    template = dir_home / "index.html"
    with template.open("w") as file:
        file.write("<html>Hello, <a href='{{ url_for('homepage') }}'>world</a></html>")

    async def homepage(request):
        return templates.TemplateResponse("index.html", {"request": request})

    dir_A: Path = dir_home.parent.resolve() / "A"
    dir_A.mkdir()
    template_A = dir_A / "template_A.html"
    with template_A.open("w") as file:
        file.write("<html>Hello, <a href='{{ url_for('get_A') }}'></a> A</html>")

    async def get_A(request):
        return templates.TemplateResponse("template_A.html", {"request": request})

    app = Starlette(
        debug=True,
        routes=[Route("/", endpoint=homepage), Route("/A", endpoint=get_A)],
    )
    templates = Jinja2Templates(directory=[dir_home, dir_A])

    assert dir_home != dir_A
    with pytest.raises(ValueError):
        dir_home.relative_to(dir_A)
    with pytest.raises(ValueError):
        assert not dir_A.relative_to(dir_home)

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "<html>Hello, <a href='http://testserver/'>world</a></html>"
    assert response.template.name == "index.html"
    assert set(response.context.keys()) == {"request"}

    response_A = client.get("/A")
    assert response_A.text == "<html>Hello, <a href='http://testserver/A'></a> A</html>"
    assert response_A.template.name == "template_A.html"
    assert set(response_A.context.keys()) == {"request"}

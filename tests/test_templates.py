import os

from starlette.applications import Starlette
from starlette.endpoints import TemplateEndpoint
from starlette.responses import HTMLResponse
from starlette.testclient import TestClient


def get_template_app(tmpdir, content):
    path = os.path.join(tmpdir, "index.html")
    with open(path, "w") as file:
        file.write(content)

    app = Starlette(debug=True, template_directory=tmpdir)
    return app


def test_templates(tmpdir):
    app = get_template_app(
        tmpdir,
        content="<html>Hello, <a href='{{ url_for('homepage') }}'>world</a></html>",
    )

    @app.route("/")
    async def homepage(request):
        template = app.get_template("index.html")
        content = template.render(request=request)
        return HTMLResponse(content)

    client = TestClient(app)
    response = client.get("/")

    assert response.text == "<html>Hello, <a href='http://testserver/'>world</a></html>"


def test_template_endpoint(tmpdir):

    app = get_template_app(
        tmpdir,
        content="<html>Hello, <a href='{{ url_for('TemplateHomepage') }}'>world</a></html>",
    )

    @app.route("/")
    class TemplateHomepage(TemplateEndpoint):

        template_name = "index.html"

    client = TestClient(app)
    response = client.get("/")
    # assert response.template == "index.html"
    # assert "request" in response.context
    assert response.text == "<html>Hello, <a href='http://testserver/'>world</a></html>"


def test_template_endpoint_context(tmpdir):

    app = get_template_app(tmpdir, content="<html>{{ greeting }}</html>")

    @app.route("/users/{username}")
    class TemplateHomepage(TemplateEndpoint):

        template_name = "index.html"

        def get_context(self, request):
            context = super().get_context(request)
            username = request.path_params["username"]
            greeting = f"Hello, {username}."
            context["greeting"] = greeting
            return context

    client = TestClient(app)
    response = client.get("/users/tomchristie")
    # assert response.template == "index.html"
    # assert "request" in response.context
    # assert "greeting" in response.context
    assert response.text == "<html>Hello, tomchristie.</html>"

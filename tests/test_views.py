import pytest
from starlette import App
from starlette.views import View
from starlette.response import PlainTextResponse
from starlette.testclient import TestClient


app = App()


class HomepageView(View):
    async def get(self, request, **kwargs):
        username = kwargs.get("username")
        if username:
            response = PlainTextResponse(f"Hello, {username}!")
        else:
            response = PlainTextResponse("Hello, world!")
        return response


app.add_route("/", HomepageView())
app.add_route("/user/{username}", HomepageView())
app.add_route("/no-method", View())


client = TestClient(app)


def test_route():
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "Hello, world!"


def test_route_kwargs():
    response = client.get("/user/tomchristie")
    assert response.status_code == 200
    assert response.text == "Hello, tomchristie!"


def test_route_method():
    response = client.post("/")
    assert response.status_code == 406
    assert response.text == "Method not allowed"


def test_method_missing():
    response = client.get("/no-method")
    assert response.status_code == 404
    assert response.text == "Not found"

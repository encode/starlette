from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def test_trusted_host_middleware() -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK", status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["testserver", "*.testserver"])],
    )

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200

    client = TestClient(app, base_url="http://subdomain.testserver")
    response = client.get("/")
    assert response.status_code == 200

    client = TestClient(app, base_url="http://invalidhost")
    response = client.get("/")
    assert response.status_code == 400


def test_default_allowed_hosts() -> None:
    app = Starlette()
    middleware = TrustedHostMiddleware(app)
    assert middleware.allowed_hosts == ["*"]


def test_www_redirect() -> None:
    def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK", status_code=200)

    app = Starlette(
        routes=[Route("/", endpoint=homepage)],
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["www.example.com"])],
    )

    client = TestClient(app, base_url="https://example.com")
    response = client.get("/")
    assert response.status_code == 200
    assert response.url == "https://www.example.com/"

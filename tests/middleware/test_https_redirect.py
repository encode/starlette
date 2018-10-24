from starlette.applications import Starlette
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient
from starlette import status


def test_https_redirect_middleware():
    app = Starlette()

    app.add_middleware(HTTPSRedirectMiddleware)

    @app.route("/")
    def homepage(request):
        return PlainTextResponse("OK", status_code=status.HTTP_200_OK)

    client = TestClient(app, base_url="https://testserver")
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK

    client = TestClient(app)
    response = client.get("/", allow_redirects=False)
    assert response.status_code == status.HTTP_301_MOVED_PERMANENTLY
    assert response.headers["location"] == "https://testserver/"

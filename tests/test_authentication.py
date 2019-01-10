import base64
import binascii

from starlette.applications import Starlette
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
    requires,
)
from starlette.endpoints import HTTPEndpoint
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.schemas import OpenAPIResponse, SchemaGenerator


class BasicAuth(AuthenticationBackend):
    async def authenticate(self, request):
        if "Authorization" not in request.headers:
            return None

        auth = request.headers["Authorization"]
        try:
            scheme, credentials = auth.split()
            decoded = base64.b64decode(credentials).decode("ascii")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationError("Invalid basic auth credentials")

        username, _, password = decoded.partition(":")
        return AuthCredentials(["authenticated"]), SimpleUser(username)


app = Starlette()
app.add_middleware(AuthenticationMiddleware, backend=BasicAuth())


@app.route("/")
def homepage(request):
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "user": request.user.display_name,
        }
    )


@app.route("/dashboard")
@requires("authenticated")
async def dashboard(request):
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "user": request.user.display_name,
        }
    )


@app.route("/admin")
@requires("authenticated", redirect="homepage")
async def admin(request):
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "user": request.user.display_name,
        }
    )


@app.route("/dashboard/sync")
@requires("authenticated")
def dashboard(request):
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "user": request.user.display_name,
        }
    )


@app.route("/admin/sync")
@requires("authenticated", redirect="homepage")
def admin(request):
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "user": request.user.display_name,
        }
    )


def test_user_interface():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"authenticated": False, "user": ""}

        response = client.get("/", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user": "tomchristie"}


def test_authentication_required():
    with TestClient(app) as client:
        response = client.get("/dashboard")
        assert response.status_code == 403

        response = client.get("/dashboard", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user": "tomchristie"}

        response = client.get("/dashboard/sync")
        assert response.status_code == 403

        response = client.get("/dashboard/sync", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user": "tomchristie"}

        response = client.get("/dashboard", headers={"Authorization": "basic foobar"})
        assert response.status_code == 400
        assert response.text == "Invalid basic auth credentials"


def test_authentication_redirect():
    with TestClient(app) as client:
        response = client.get("/admin")
        assert response.status_code == 200
        assert response.url == "http://testserver/"

        response = client.get("/admin", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user": "tomchristie"}

        response = client.get("/admin/sync")
        assert response.status_code == 200
        assert response.url == "http://testserver/"

        response = client.get("/admin/sync", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user": "tomchristie"}


def on_auth_error(request: Request, exc: Exception):
    return JSONResponse({"error": str(exc)}, status_code=401)


other_app = Starlette()
other_app.add_middleware(
    AuthenticationMiddleware, backend=BasicAuth(), on_error=on_auth_error
)


@other_app.route("/control-panel")
@requires("authenticated")
def control_panel(request):
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "user": request.user.display_name,
        }
    )


def test_custom_on_error():
    with TestClient(other_app) as client:
        response = client.get("/control-panel", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user": "tomchristie"}

        response = client.get(
            "/control-panel", headers={"Authorization": "basic foobar"}
        )
        assert response.status_code == 401
        assert response.json() == {"error": "Invalid basic auth credentials"}


api_app = Starlette()
api_app.add_middleware(AuthenticationMiddleware, backend=BasicAuth())
api_app.schema_generator = SchemaGenerator(
    {"openapi": "3.0.0", "info": {"title": "Example API", "version": "1.0"}}
)


@api_app.route("/manage", name="manage")
@requires("authenticated")
class ManageResources(HTTPEndpoint):
    def get(self, request):
        """
        summary: list manageable resources
        responses:
          200:
            description: successful operation
          403:
            description: forbidden
        """
        return JSONResponse(
            [
                {
                    "id": 1,
                    "name": "users",
                },
                {
                    "id": 2,
                    "name": "organizations",
                },
            ]
        )


@api_app.route("/users/{user_id}")
@requires("authenticated", redirect="manage")
class ManageUsers(HTTPEndpoint):
    def delete(self, request):
        """
        summary: delete a user
        responses:
          200:
            description: successful operation or redirect
        """
        return JSONResponse({"deleted": request.path_params['user_id']})


def test_management_api():
    assert api_app.schema == {
        'openapi': '3.0.0',
        'info': {
            'title': 'Example API',
            'version': '1.0'
        },
        'paths': {
            '/manage': {
                'get': {
                    'summary': 'list manageable resources',
                    'responses': {
                        200: {
                            'description': 'successful operation'
                        },
                        403: {
                            'description': 'forbidden'
                        }
                    }
                }
            },
            '/users/{user_id}': {
                'delete': {
                    'summary': 'delete a user',
                    'responses': {
                        200: {
                            'description': 'successful operation or redirect'
                        }
                    }
                }
            }
        }
    }
    with TestClient(api_app) as client:
        response = client.get("/manage")
        assert response.status_code == 403

        response = client.get("/manage", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json() == [{"id": 1, "name": "users"}, {"id": 2, "name": "organizations"}]

        response = client.delete("/users/1")
        assert response.status_code == 302
        assert response.headers['location'] == 'http://testserver/manage'

        response = client.delete("/users/123", auth=("tomchristie", "example"))
        assert response.status_code == 200
        assert response.json()['deleted'] == '123'

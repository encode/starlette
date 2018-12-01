import pytest

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.middleware.resource import ResourceMiddleware
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


class Store:
    def get_last_order(self):
        return "3 apples"

    def close(self):
        pass


class StoreMiddleware(ResourceMiddleware):
    async def get_resource(self, scope):
        return Store()

    async def clean_resource(self, resource):
        resource.close()

    async def startup(self) -> None:
        pass  # for example, create a connection pool

    async def shutdown(self) -> None:
        pass  # and close the connection pool


class AuthMiddleware(ResourceMiddleware):
    async def get_resource(self, scope):
        headers = Headers(scope=scope)
        return "Jane" if headers.get("Authorization") == "Bearer 123" else None


def test_resource_middlewares():
    app = Starlette()
    app.add_middleware(StoreMiddleware, name="store")
    app.add_middleware(AuthMiddleware, name="user")

    @app.route("/last-order")
    def last_order(request):
        user = request.resource("user")
        store = request.resource("store")

        if user is None:
            return JSONResponse({})

        return JSONResponse({"customer": user, "lastOrder": store.get_last_order()})

    with TestClient(app) as client:
        response = client.get("/last-order")
        assert response.json() == {}
        response = client.get("/last-order", headers={"Authorization": "Bearer 123"})
        assert response.json() == {"customer": "Jane", "lastOrder": "3 apples"}


def test_double_resource_registration():
    app = Starlette()
    app.add_middleware(StoreMiddleware, name="store")
    app.add_middleware(AuthMiddleware, name="store")

    @app.route("/last-order")
    def last_order(request):
        return JSONResponse({})  # pragma: no cover

    with TestClient(app) as client:
        with pytest.raises(ValueError):
            client.get("/last-order")

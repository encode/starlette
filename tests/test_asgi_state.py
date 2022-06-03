import warnings
from typing import Callable

import pytest

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient


def test_scope_key_deprecation(
    test_client_factory: Callable[[Starlette], TestClient]
) -> None:
    async def route_accesses_deprecated_key(request: Request) -> Response:
        app = request.scope["app"]
        request.scope["app"] = app
        return Response()

    async def route_accesses_extension_key(request: Request) -> Response:
        app = request.scope["extensions"]["starlette"]["app"]
        request.scope["extensions"]["starlette"]["app"] = app
        return Response()

    app = Starlette(
        routes=[
            Route("/good", route_accesses_extension_key),
            Route("/bad", route_accesses_deprecated_key),
        ]
    )
    client = test_client_factory(app)

    with pytest.warns(DeprecationWarning, match=r"scope\[\"app\"\] is deprecated"):
        client.get("/bad")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        client.get("/good")

import functools

import pytest
from asgiref.typing import HTTPScope, WebSocketScope

from starlette.testclient import TestClient, asgi_version


@pytest.fixture
def no_trio_support(anyio_backend_name):
    if anyio_backend_name == "trio":
        pytest.skip("Trio not supported (yet!)")


@pytest.fixture
def test_client_factory(anyio_backend_name, anyio_backend_options):
    # anyio_backend_name defined by:
    # https://anyio.readthedocs.io/en/stable/testing.html#specifying-the-backends-to-run-on
    return functools.partial(
        TestClient,
        backend=anyio_backend_name,
        backend_options=anyio_backend_options,
    )


@pytest.fixture
def http_scope() -> HTTPScope:
    return HTTPScope(
        type="http",
        asgi=asgi_version,
        http_version="1.1",
        method="GET",
        scheme="https",
        path="/path/to/somewhere",
        raw_path="/path/to/somewhere".encode(),
        root_path="",
        query_string=b"abc=123",
        headers=[],
        client=None,
        server=None,
        extensions=None,
    )


@pytest.fixture
def websocket_scope() -> WebSocketScope:
    return WebSocketScope(
        type="websocket",
        asgi=asgi_version,
        http_version="1.1",
        scheme="ws",
        path="/abc/",
        raw_path="/abc/".encode(),
        root_path="",
        query_string=b"",
        headers=[],
        client=None,
        server=None,
        subprotocols=[],
        extensions=None,
    )

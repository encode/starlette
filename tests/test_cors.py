from starlette.responses import Response
from starlette.cors import CORSMiddleware
from starlette.testclient import TestClient
import asyncio

cors_headers = [
    "access-control-allow-origin",
    "access-control-expose-headers",
    "access-control-allow-credentials",
    "access-control-allow-headers",
    "access-control-allow-methods",
    "access-control-max-age",
]


def test_cors_headers_exist():
    def app(scope):
        async def asgi(receive, send):
            response = Response("hello, world", media_type="text/plain")
            await response(receive, send)

        return asgi

    client = TestClient(CORSMiddleware(app))
    response = client.get("/")
    for header in cors_headers:
        assert header in response.headers.keys()

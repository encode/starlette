from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.testclient import TestClient
import os


class ForceMultipartDict(dict):
    def __bool__(self):
        return True


# FORCE_MULTIPART is an empty dict that boolean-evaluates as `True`.
FORCE_MULTIPART = ForceMultipartDict()


def test_multipart_request_data(tmpdir):
    def app(scope):
        async def asgi(receive, send):
            request = Request(scope, receive)
            data = {"form": await request.form()}
            response = JSONResponse(data)
            await response(receive, send)

        return asgi

    client = TestClient(app)
    response = client.post("/", data={"some": "data"}, files=FORCE_MULTIPART)
    assert response.json() == {"form": {"some": "data"}}

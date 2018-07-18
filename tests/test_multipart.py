from starlette import Request, TestClient, JSONResponse
import os


def test_multipart_request(tmpdir):
    def app(scope):
        async def asgi(receive, send):
            request = Request(scope, receive)
            data = {"form": await request.form()}
            response = JSONResponse(data)
            await response(receive, send)

        return asgi

    path = os.path.join(tmpdir, "test.txt")
    with open(path, "wb") as file:
        file.write(b"<file content>")

    client = TestClient(app)
    response = client.post("/", data={"some": "data"}, files={"test": path})
    assert response.json() == {"form": {"some": "data"}}

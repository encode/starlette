import asyncio
import os

import pytest

from starlette import status
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
    UJSONResponse,
)
from starlette.testclient import TestClient


def test_text_response():
    async def app(scope, receive, send):
        response = Response("hello, world", media_type="text/plain")
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "hello, world"


def test_bytes_response():
    async def app(scope, receive, send):
        response = Response(b"xxxxx", media_type="image/png")
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.content == b"xxxxx"


def test_ujson_response():
    async def app(scope, receive, send):
        response = UJSONResponse({"hello": "world"})
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.json() == {"hello": "world"}


def test_redirect_response():
    async def app(scope, receive, send):
        if scope["path"] == "/":
            response = Response("hello, world", media_type="text/plain")
        else:
            response = RedirectResponse("/")
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/redirect")
    assert response.text == "hello, world"
    assert response.url == "http://testserver/"


def test_streaming_response():
    filled_by_bg_task = ""

    async def app(scope, receive, send):
        async def numbers(minimum, maximum):
            for i in range(minimum, maximum + 1):
                yield str(i)
                if i != maximum:
                    yield ", "
                await asyncio.sleep(0)

        async def numbers_for_cleanup(start=1, stop=5):
            nonlocal filled_by_bg_task
            async for thing in numbers(start, stop):
                filled_by_bg_task = filled_by_bg_task + thing

        cleanup_task = BackgroundTask(numbers_for_cleanup, start=6, stop=9)
        generator = numbers(1, 5)
        response = StreamingResponse(
            generator, media_type="text/plain", background=cleanup_task
        )
        await response(scope, receive, send)

    assert filled_by_bg_task == ""
    client = TestClient(app)
    response = client.get("/")
    assert response.text == "1, 2, 3, 4, 5"
    assert filled_by_bg_task == "6, 7, 8, 9"


def test_sync_streaming_response():
    async def app(scope, receive, send):
        def numbers(minimum, maximum):
            for i in range(minimum, maximum + 1):
                yield str(i)
                if i != maximum:
                    yield ", "

        generator = numbers(1, 5)
        response = StreamingResponse(generator, media_type="text/plain")
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "1, 2, 3, 4, 5"


def test_response_headers():
    async def app(scope, receive, send):
        headers = {"x-header-1": "123", "x-header-2": "456"}
        response = Response("hello, world", media_type="text/plain", headers=headers)
        response.headers["x-header-2"] = "789"
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.headers["x-header-1"] == "123"
    assert response.headers["x-header-2"] == "789"


def test_response_phrase():
    app = Response(status_code=204)
    client = TestClient(app)
    response = client.get("/")
    assert response.reason == "No Content"

    app = Response(b"", status_code=123)
    client = TestClient(app)
    response = client.get("/")
    assert response.reason == ""


def test_file_response(tmpdir):
    path = os.path.join(tmpdir, "xyz")
    content = b"<file content>" * 1000
    with open(path, "wb") as file:
        file.write(content)

    filled_by_bg_task = ""

    async def numbers(minimum, maximum):
        for i in range(minimum, maximum + 1):
            yield str(i)
            if i != maximum:
                yield ", "
            await asyncio.sleep(0)

    async def numbers_for_cleanup(start=1, stop=5):
        nonlocal filled_by_bg_task
        async for thing in numbers(start, stop):
            filled_by_bg_task = filled_by_bg_task + thing

    cleanup_task = BackgroundTask(numbers_for_cleanup, start=6, stop=9)

    async def app(scope, receive, send):
        response = FileResponse(
            file_or_path=path, filename="example.png", background=cleanup_task
        )
        await response(scope, receive, send)

    assert filled_by_bg_task == ""
    client = TestClient(app)
    response = client.get("/")
    expected_disposition = 'attachment; filename="example.png"'
    assert response.status_code == status.HTTP_200_OK
    assert response.content == content
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == expected_disposition
    assert "content-length" in response.headers
    assert "last-modified" in response.headers
    assert "etag" in response.headers
    assert filled_by_bg_task == "6, 7, 8, 9"


def test_file_like_response(tmpdir):
    path = os.path.join(tmpdir, "xyz")
    content = b"<file content>" * 1000
    with open(path, "wb") as file:
        file.write(content)

    async def app(scope, receive, send):
        with open(path, "rb") as file_like:
            response = FileResponse(file_or_path=file_like)
            await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.content == content
    assert response.headers["content-type"] == "application/octet-stream"
    assert "content-disposition" not in response.headers
    assert "content-length" not in response.headers
    assert "last-modified" not in response.headers
    assert "etag" not in response.headers


def test_file_response_with_directory_raises_error(tmpdir):
    app = FileResponse(file_or_path=str(tmpdir), filename="example.png")
    client = TestClient(app)
    with pytest.raises(RuntimeError) as exc:
        client.get("/")
    assert "is not a file" in str(exc)


def test_file_response_with_missing_file_raises_error(tmpdir):
    path = os.path.join(tmpdir, "404.txt")
    app = FileResponse(file_or_path=path, filename="404.txt")
    client = TestClient(app)
    with pytest.raises(RuntimeError) as exc:
        client.get("/")
    assert "does not exist" in str(exc)


def test_file_response_reading_error_raises_error():
    class FakeFile:
        def read(self):
            raise ValueError("No content here")  # pragma: no cover

        def close(self):
            pass

    app = FileResponse(file_or_path=FakeFile())
    client = TestClient(app)
    with pytest.raises(RuntimeError) as exc:
        client.get("/")
    assert "Error processing file in FileResponse" in str(exc)


def test_set_cookie():
    async def app(scope, receive, send):
        response = Response("Hello, world!", media_type="text/plain")
        response.set_cookie(
            "mycookie",
            "myvalue",
            max_age=10,
            expires=10,
            path="/",
            domain="localhost",
            secure=True,
            httponly=True,
        )
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.text == "Hello, world!"


def test_delete_cookie():
    async def app(scope, receive, send):
        request = Request(scope, receive)
        response = Response("Hello, world!", media_type="text/plain")
        if request.cookies.get("mycookie"):
            response.delete_cookie("mycookie")
        else:
            response.set_cookie("mycookie", "myvalue")
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.cookies["mycookie"]
    response = client.get("/")
    assert not response.cookies.get("mycookie")


def test_populate_headers():
    app = Response(content="hi", headers={}, media_type="text/html")
    client = TestClient(app)
    response = client.get("/")
    assert response.text == "hi"
    assert response.headers["content-length"] == "2"
    assert response.headers["content-type"] == "text/html; charset=utf-8"


def test_head_method():
    app = Response("hello, world", media_type="text/plain")
    client = TestClient(app)
    response = client.head("/")
    assert response.text == ""

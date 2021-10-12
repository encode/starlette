"""Test scenarios where the response is aborted while streaming

These scenarios are tested with regard to the effect on
 - Background Tasks: should always execute
 - On Complete Tasks: should only execute if disconnect is received after stream is
   completed
"""

import os
import random
import socket
import tempfile
import time
from multiprocessing import Process
from typing import AsyncGenerator

import anyio
import pytest
import requests
import uvicorn

from starlette import status
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse
from starlette.routing import Route


def get_free_port() -> int:
    "Get next free ephemeral tcp/udp port"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    address = ("127.0.0.1", random.randint(49152, 65535))
    while not s.connect_ex(address):
        address = ("127.0.0.1", random.randint(49152, 65535))
    s.close()
    return address[1]


BG = ""
OC = ""
CONTENT = b"<file content>" * 1000
PATH = os.path.join(tempfile.mkdtemp(), "xyz")

SLEEP = 0.1
HOST = "127.0.0.1"
PORT = get_free_port()


async def numbers(minimum: int, maximum: int) -> AsyncGenerator[str, None]:
    "Create numbers asynchronously with commas as seperators"
    for i in range(minimum, maximum + 1):
        yield str(i)
        if i != maximum:
            yield ", "
        await anyio.sleep(SLEEP)


async def count_out_loud(start: int = 1, stop: int = 5) -> str:
    "Generate string with list of numbers as string"
    result = ""
    async for thing in numbers(start, stop):
        result = result + thing
    return result


async def set_bg_artifact() -> None:
    """Change state of global BG variable

    This is used to track whether the Background Task is really run.
    """
    global BG
    BG = await count_out_loud(10, 15)


async def set_oc_artifact() -> None:
    """Change state of global BG variable

    This is used to track whether the on complete task is really run.
    """
    global OC
    OC = await count_out_loud(16, 20)


async def stream_response(request: Request) -> StreamingResponse:
    cleanup_task = BackgroundTask(set_bg_artifact)
    always = BackgroundTask(set_oc_artifact)
    generator = numbers(1, 5)
    return StreamingResponse(
        generator,
        media_type="text/plain",
        on_complete=cleanup_task,
        background=always,
    )


async def stream_file_response(request: Request) -> FileResponse:
    cleanup_task = BackgroundTask(set_bg_artifact)
    always = BackgroundTask(set_oc_artifact)
    return FileResponse(
        path=PATH, filename="example.png", on_complete=cleanup_task, background=always
    )


async def bg_route(request: Request) -> Response:
    "Return the value of BG to verify if Background task was executed"
    return Response(f"{BG}", media_type="text/plain")


async def oc_route(request: Request) -> Response:
    "Return the value of OC to verify if On Complete was executed"
    return Response(f"{OC}", media_type="text/plain")


def run_server():
    app = Starlette(
        debug=True,
        routes=[
            Route("/", stream_response),
            Route("/bg", bg_route),
            Route("/oc", oc_route),
            Route("/file", stream_file_response),
        ],
    )
    uvicorn.run(app, host=HOST, port=PORT)


@pytest.fixture
def server():
    """Run server in parallel thread

    This fixture also takes care of creating and removing the file used for the
    FileResponse.
    """
    # Setup Test
    with open(PATH, "wb") as file:
        file.write(CONTENT)
    proc = Process(target=run_server, args=(), daemon=True)
    proc.start()
    time.sleep(10 * SLEEP)
    if proc.exitcode:
        os.remove(PATH)
        raise RuntimeError("Process could not start")
    # Execute Test
    yield
    # Cleanup after test
    os.remove(PATH)
    proc.terminate()
    time.sleep(10 * SLEEP)
    proc.close()


def test_streaming_response_abort(server):
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert check.status_code == status.HTTP_200_OK
    assert check.content == b""

    resp = requests.get(
        f"http://{HOST}:{PORT}",
        stream=True,
    )
    resp.close()

    assert resp.status_code == 200
    assert resp.content == b""

    time.sleep(10 * SLEEP)
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert resp.status_code == 200
    assert check.content == b""

    check = requests.get(f"http://{HOST}:{PORT}/oc")
    assert check.status_code == 200
    assert check.content == b"16, 17, 18, 19, 20"


def test_streaming_response_complete(server):
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert check.status_code == status.HTTP_200_OK
    assert check.content == b""

    resp = requests.get(
        f"http://{HOST}:{PORT}",
        stream=True,
    )
    time.sleep(10 * SLEEP)
    resp.close()

    assert resp.status_code == 200
    assert resp.content == b""

    time.sleep(10 * SLEEP)
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert resp.status_code == 200
    assert check.content == b"10, 11, 12, 13, 14, 15"

    check = requests.get(f"http://{HOST}:{PORT}/oc")
    assert check.status_code == 200
    assert check.content == b"16, 17, 18, 19, 20"


def test_file_response_abort(server):
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert check.status_code == status.HTTP_200_OK
    assert check.content == b""

    response = requests.get(
        f"http://{HOST}:{PORT}/file",
        stream=True,
    )
    response.close()

    assert response.content == b""
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "image/png"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="example.png"'
    )
    assert "content-length" in response.headers
    assert "last-modified" in response.headers
    assert "etag" in response.headers

    time.sleep(10 * SLEEP)
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert check.status_code == status.HTTP_200_OK
    assert check.content == b""

    check = requests.get(f"http://{HOST}:{PORT}/oc")
    assert check.status_code == 200
    assert check.content == b"16, 17, 18, 19, 20"


def test_file_response_complete(server):
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert check.status_code == status.HTTP_200_OK
    assert check.content == b""

    response = requests.get(f"http://{HOST}:{PORT}/file", stream=True)
    time.sleep(10 * SLEEP)
    response.close()

    assert response.content == b""
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "image/png"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="example.png"'
    )
    assert "content-length" in response.headers
    assert "last-modified" in response.headers
    assert "etag" in response.headers

    time.sleep(10 * SLEEP)
    check = requests.get(f"http://{HOST}:{PORT}/bg")
    assert check.status_code == status.HTTP_200_OK
    assert check.content == b"10, 11, 12, 13, 14, 15"

    check = requests.get(f"http://{HOST}:{PORT}/oc")
    assert check.status_code == 200
    assert check.content == b"16, 17, 18, 19, 20"

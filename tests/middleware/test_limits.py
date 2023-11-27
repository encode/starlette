from typing import AsyncGenerator, Callable

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.limits import ContentTooLarge, LimitRequestSizeMiddleware
from starlette.requests import Request
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send


async def echo_app(scope: Scope, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        more_body = message.get("more_body", False)
        body = message.get("body", b"")

        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body, "more_body": more_body})

        if not more_body:
            break


app = LimitRequestSizeMiddleware(echo_app, max_body_size=1024)


def test_no_op(test_client_factory: Callable[..., TestClient]) -> None:
    client = test_client_factory(app)

    response = client.post("/", content="Small payload")
    assert response.status_code == 200
    assert response.text == "Small payload"


def test_content_too_large(test_client_factory: Callable[..., TestClient]) -> None:
    client = test_client_factory(app)

    response = client.post("/", content="X" * 1025)
    assert response.status_code == 413
    assert response.text == "Content Too Large"


def test_content_too_large_on_streaming_body(
    test_client_factory: Callable[..., TestClient]
) -> None:
    client = test_client_factory(app)

    response = client.post("/", content=[b"X" * 1025])
    assert response.status_code == 413
    assert response.text == "Content Too Large"


@pytest.mark.anyio
async def test_content_too_large_on_started_response() -> None:
    scope: Scope = {"type": "http", "method": "POST", "path": "/", "headers": []}

    async def receive() -> AsyncGenerator[Message, None]:
        yield {"type": "http.request", "body": b"X" * 1024, "more_body": True}
        yield {"type": "http.request", "body": b"X", "more_body": False}

    async def send(message: Message) -> None:
        ...

    rcv = receive()

    with pytest.raises(ContentTooLarge) as ctx:
        await app(scope, rcv.__anext__, send)
    assert ctx.value.max_body_size == 1024

    await rcv.aclose()


def test_content_too_large_on_starlette(
    test_client_factory: Callable[..., TestClient]
) -> None:
    async def read_body_endpoint(request: Request) -> None:
        await request.body()

    app = Starlette(
        routes=[Route("/", read_body_endpoint, methods=["POST"])],
        middleware=[Middleware(LimitRequestSizeMiddleware, max_body_size=1024)],
    )
    client = test_client_factory(app)

    response = client.post("/", content=[b"X" * 1024, b"X"])
    assert response.status_code == 413
    assert response.text == "Content Too Large"


def test_content_too_large_and_content_length_mismatch(
    test_client_factory: Callable[..., TestClient]
) -> None:
    client = test_client_factory(app)

    response = client.post("/", content="X" * 1025, headers={"Content-Length": "1024"})
    assert response.status_code == 413
    assert response.text == "Content Too Large"

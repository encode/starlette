from typing import AsyncGenerator, Callable

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.limits import ContentTooLarge, LimitBodySizeMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route
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


app = LimitBodySizeMiddleware(echo_app, max_body_size=1024)


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


async def read_body_endpoint(request: Request) -> Response:
    body = b""
    async for chunk in request.stream():
        body += chunk
    return Response(content=body)


def test_content_too_large_on_starlette(
    test_client_factory: Callable[..., TestClient]
) -> None:
    app = Starlette(
        routes=[Route("/", read_body_endpoint, methods=["POST"])],
        middleware=[Middleware(LimitBodySizeMiddleware, max_body_size=1024)],
    )
    client = test_client_factory(app)

    response = client.post("/", content=b"X" * 1024)
    assert response.status_code == 200
    assert response.text == "X" * 1024

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


def test_inner_middleware_overrides_outer_middleware(
    test_client_factory: Callable[..., TestClient]
) -> None:
    outer_app = LimitBodySizeMiddleware(
        LimitBodySizeMiddleware(
            echo_app,
            max_body_size=2048,
        ),
        max_body_size=1024,
    )

    client = test_client_factory(outer_app)

    response = client.post("/", content="X" * 2049)
    assert response.status_code == 413
    assert response.text == "Content Too Large"

    response = client.post("/", content="X" * 2048)
    assert response.status_code == 200
    assert response.text == "X" * 2048


def test_multiple_middleware_on_starlette(
    test_client_factory: Callable[..., TestClient]
) -> None:
    app = Starlette(
        routes=[
            Route("/outer", read_body_endpoint, methods=["POST"]),
            Mount(
                "/inner",
                routes=[Route("/", read_body_endpoint, methods=["POST"])],
                middleware=[Middleware(LimitBodySizeMiddleware, max_body_size=2048)],
            ),
        ],
        middleware=[Middleware(LimitBodySizeMiddleware, max_body_size=1024)],
    )
    client = test_client_factory(app)

    # response = client.post("/outer", content="X" * 1025)
    # assert response.status_code == 413
    # assert response.text == "Content Too Large"

    # response = client.post("/outer", content="X" * 1025)
    # assert response.status_code == 413
    # assert response.text == "Content Too Large"

    response = client.post("/inner", content="X" * 1025)
    assert response.status_code == 200
    assert response.text == "X" * 1025

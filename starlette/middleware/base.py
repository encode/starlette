import typing

import anyio

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp, Receive, Scope, Send

RequestResponseEndpoint = typing.Callable[[Request], typing.Awaitable[Response]]
DispatchFunction = typing.Callable[
    [Request, RequestResponseEndpoint], typing.Awaitable[Response]
]


class BaseHTTPMiddleware:
    def __init__(self, app: ASGIApp, dispatch: DispatchFunction = None) -> None:
        self.app = app
        self.dispatch_func = self.dispatch if dispatch is None else dispatch

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        response = await self.dispatch_func(request, self.call_next)
        await response(scope, receive, send)

    async def call_next(self, request: Request) -> Response:
        send_stream, recv_stream = anyio.create_memory_object_stream()
        scope = request.scope
        task_group = scope["task_group"]

        async def coro() -> None:
            async with send_stream:
                await self.app(scope, request.receive, send_stream.send)

        task_group.spawn(coro)

        try:
            message = await recv_stream.receive()
        except anyio.EndOfStream:
            raise RuntimeError("No response returned.")

        assert message["type"] == "http.response.start"

        async def body_stream() -> typing.AsyncGenerator[bytes, None]:
            async with recv_stream:
                async for message in recv_stream:
                    assert message["type"] == "http.response.body"
                    yield message.get("body", b"")

        response = StreamingResponse(
            status_code=message["status"], content=body_stream()
        )
        response.raw_headers = message["headers"]
        return response

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raise NotImplementedError()  # pragma: no cover

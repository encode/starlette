import asyncio
import typing

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
        loop = asyncio.get_event_loop()
        queue: "asyncio.Queue[typing.Optional[Message]]" = asyncio.Queue(maxsize=1)

        scope = request.scope
        receive = request.receive
        send = queue.put

        async def coro() -> None:
            try:
                await self.app(scope, receive, send)
            finally:
                await queue.put(None)

        task = loop.create_task(coro())
        message = await queue.get()
        if message is None:
            task.result()
            raise RuntimeError("No response returned.")
        assert message["type"] == "http.response.start"
        status = message["status"]
        headers = message["headers"]

        first_body_message = await queue.get()
        if first_body_message is None:
            task.result()
            raise RuntimeError("Empty response body returned")
        assert first_body_message["type"] == "http.response.body"
        response_body_start = first_body_message.get("body", b"")

        async def body_stream() -> typing.AsyncGenerator[bytes, None]:
            # In non-streaming responses, there should be one message to emit
            yield response_body_start
            message = first_body_message
            while message and message.get("more_body"):
                message = await queue.get()
                if message is None:
                    break
                assert message["type"] == "http.response.body"
                yield message.get("body", b"")

            if task.done():
                # Check for exceptions and raise if present.
                # Incomplete tasks may still have background tasks to run.
                task.result()

        # Assume non-streaming and start with a regular response
        response: typing.Union[Response, StreamingResponse] = Response(
            status_code=status, content=response_body_start
        )

        if first_body_message.get("more_body"):
            response = StreamingResponse(status_code=status, content=body_stream())

        response.raw_headers = headers
        return response

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raise NotImplementedError()  # pragma: no cover

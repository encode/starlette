import asyncio
import typing

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp, Receive, Scope, Send

try:
    from asyncio.exceptions import InvalidStateError  # type: ignore
except ImportError:  # pragma: nocover
    from asyncio import InvalidStateError


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
        queue = asyncio.Queue(maxsize=1)  # type: asyncio.Queue

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
            queue.task_done()
            task.result()
            raise RuntimeError("No response returned.")
        assert message["type"] == "http.response.start"

        async def body_stream() -> typing.AsyncGenerator[bytes, None]:
            def streaming_predicate(
                msg: typing.Optional[dict], more_body: bool = True
            ) -> bool:
                return (
                    msg is not None
                    and msg["type"] == "http.response.body"
                    and "more_body" in msg
                    and msg["more_body"] is more_body
                )

            # In non-streaming responses, there will be one message to emit
            message = await queue.get()
            if message is not None:
                queue.task_done()
                assert message["type"] == "http.response.body"
                yield message.get("body", b"")

            while streaming_predicate(message, more_body=True):
                message = await queue.get()
                queue.task_done()
                if message is None:
                    break
                assert message["type"] == "http.response.body"
                yield message.get("body", b"")

            try:
                task.result()  # check for exceptions and raise if present
            except InvalidStateError:
                # task is not completed (which could be due to background)
                pass

        response = StreamingResponse(
            status_code=message["status"], content=body_stream()
        )
        response.raw_headers = message["headers"]
        return response

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raise NotImplementedError()  # pragma: no cover

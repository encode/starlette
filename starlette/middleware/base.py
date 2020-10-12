import asyncio
import typing

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

RequestResponseEndpoint = typing.Callable[[Request], typing.Awaitable[Response]]
DispatchFunction = typing.Callable[
    [Request, RequestResponseEndpoint], typing.Awaitable[Response]
]


class _StreamingTemplateResponse(StreamingResponse):
    template: str
    context: dict

    def __init__(
        self, content: typing.Any, template: str, context: dict, status_code: int
    ):
        super().__init__(content, status_code, None, None, None)
        self.template = template
        self.context = context

    async def stream_response(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.template",
                "template": self.template,
                "context": self.context,
            }
        )
        await super().stream_response(send)


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
        queue: "asyncio.Queue[typing.Optional[Message]]" = asyncio.Queue()

        scope = request.scope
        receive = request.receive
        send = queue.put

        async def coro() -> None:
            try:
                await self.app(scope, receive, send)
            finally:
                await queue.put(None)

        task = loop.create_task(coro())

        async def body_stream() -> typing.AsyncGenerator[bytes, None]:
            while True:
                message = await queue.get()
                if message is None:
                    break
                assert message["type"] == "http.response.body"
                yield message.get("body", b"")
            task.result()

        message = await queue.get()
        if message is None:
            task.result()
            raise RuntimeError("No response returned.")

        response: Response

        extensions = request.scope.get("extensions")
        if (
            extensions is not None
            and "http.response.template" in extensions
            and message["type"] == "http.response.template"
        ):
            template = message["template"]
            context = message["context"]
            message = await queue.get()
            assert message is not None
            assert message["type"] == "http.response.start"
            response = _StreamingTemplateResponse(
                template=template,
                context=context,
                status_code=message["status"],
                content=body_stream(),
            )
        else:
            assert message["type"] == "http.response.start"
            response = StreamingResponse(
                status_code=message["status"], content=body_stream()
            )

        response.raw_headers = message["headers"]
        return response

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raise NotImplementedError()  # pragma: no cover

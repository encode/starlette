"""Middleware that limits the body size of incoming requests."""
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_MAX_BODY_SIZE = 2_621_440  # 2.5MB
MAX_BODY_SIZE_KEY = "starlette.max_body_size"


class ContentTooLarge(Exception):
    def __init__(self, max_body_size: int) -> None:
        self.max_body_size = max_body_size


class SetBodySizeLimit:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope[MAX_BODY_SIZE_KEY] = self.max_body_size
        await self.app(scope, receive, send)

class LimitBodySizeMiddleware:
    def __init__(
        self, app: ASGIApp
    ) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            return await self.app(scope, receive, send)

        total_size = 0
        response_started = False
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")

        max_body_size = scope.get(MAX_BODY_SIZE_KEY, None)
        if not max_body_size:
            return await self.app(scope, receive, send)

        async def wrap_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def wrap_receive() -> Message:
            nonlocal total_size

            if content_length is not None:
                if int(content_length) > max_body_size:
                    raise ContentTooLarge(max_body_size)

            message = await receive()

            if message["type"] == "http.request":
                chunk_size = len(message["body"])
                total_size += chunk_size
                if total_size > max_body_size:
                    raise ContentTooLarge(max_body_size)

            return message

        try:
            await self.app(scope, wrap_receive, wrap_send)
        except ContentTooLarge as exc:
            # NOTE: If response has already started, we can't return a 413, because the
            #   headers have already been sent.
            if not response_started:
                response = PlainTextResponse("Content Too Large", status_code=413)
                return await response(scope, receive, send)
            raise exc

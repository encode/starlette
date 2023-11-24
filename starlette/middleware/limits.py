"""Middleware that limits the body size of incoming requests."""
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_MAX_BODY_SIZE = 2_621_440  # 2.5MB


class ContentTooLarge(Exception):
    def __init__(self, max_body_size: int) -> None:
        self.max_body_size = max_body_size


class LimitRequestMiddleware:
    def __init__(
        self, app: ASGIApp, max_body_size: int = DEFAULT_MAX_BODY_SIZE
    ) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            return await self.app(scope, receive, send)

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            if int(content_length) > self.max_body_size:
                return await _content_too_large_app(scope)(scope, receive, send)

            # NOTE: The server makes sure that the content-length header sent by the
            #   client is the same as the length of the body.
            #   Ref.: https://github.com/django/asgiref/issues/422
            return await self.app(scope, receive, send)

        total_size = 0
        response_started = False

        async def wrap_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def wrap_receive() -> Message:
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                chunk_size = len(message["body"])
                total_size += chunk_size
                if total_size > self.max_body_size:
                    raise ContentTooLarge(self.max_body_size)
            return message

        try:
            await self.app(scope, wrap_receive, wrap_send)
        except ContentTooLarge as exc:
            # NOTE: If response has already started, we can't return a 413, because the
            #   headers have already been sent.
            if not response_started:
                return await _content_too_large_app(scope)(scope, receive, send)
            raise exc


def _content_too_large_app(scope: Scope) -> PlainTextResponse:
    return PlainTextResponse("Content Too Large", status_code=413)

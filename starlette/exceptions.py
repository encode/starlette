import asyncio
import http
import typing

from starlette import status
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocket


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = None) -> None:
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase
        self.status_code = status_code
        self.detail = detail

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"{class_name}(status_code={self.status_code!r}, detail={self.detail!r})"


class WebSocketException(Exception):
    def __init__(self, code: int = status.WS_1008_POLICY_VIOLATION) -> None:
        """
        `code` defaults to 1008, from the WebSocket specification:

        > 1008 indicates that an endpoint is terminating the connection
        > because it has received a message that violates its policy.  This
        > is a generic status code that can be returned when there is no
        > other more suitable status code (e.g., 1003 or 1009) or if there
        > is a need to hide specific details about the policy.

        Set `code` to any value allowed by the
        [WebSocket specification](https://tools.ietf.org/html/rfc6455#section-7.4.1).
        """
        self.code = code


class ExceptionMiddleware:
    def __init__(
        self, app: ASGIApp, handlers: dict = None, debug: bool = False
    ) -> None:
        self.app = app
        self.debug = debug  # TODO: We ought to handle 404 cases if debug is set.
        self._status_handlers: typing.Dict[int, typing.Callable] = {}
        self._exception_handlers: typing.Dict[
            typing.Type[Exception], typing.Callable
        ] = {
            HTTPException: self.http_exception,
            WebSocketException: self.websocket_exception,
        }
        if handlers is not None:
            for key, value in handlers.items():
                self.add_exception_handler(key, value)

    def add_exception_handler(
        self,
        exc_class_or_status_code: typing.Union[int, typing.Type[Exception]],
        handler: typing.Callable,
    ) -> None:
        if isinstance(exc_class_or_status_code, int):
            self._status_handlers[exc_class_or_status_code] = handler
        else:
            assert issubclass(exc_class_or_status_code, Exception)
            self._exception_handlers[exc_class_or_status_code] = handler

    def _lookup_exception_handler(
        self, exc: Exception
    ) -> typing.Optional[typing.Callable]:
        for cls in type(exc).__mro__:
            if cls in self._exception_handlers:
                return self._exception_handlers[cls]
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        response_started = False

        async def sender(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, sender)
        except Exception as exc:
            handler = None

            if isinstance(exc, HTTPException):
                handler = self._status_handlers.get(exc.status_code)

            if handler is None:
                handler = self._lookup_exception_handler(exc)

            if handler is None:
                raise exc

            if response_started:
                msg = "Caught handled exception, but response already started."
                raise RuntimeError(msg) from exc

            if scope["type"] == "http":
                request = Request(scope, receive=receive)
                if asyncio.iscoroutinefunction(handler):
                    response = await handler(request, exc)
                else:
                    response = await run_in_threadpool(handler, request, exc)
                await response(scope, receive, sender)
            elif scope["type"] == "websocket":
                websocket = WebSocket(scope, receive=receive, send=send)
                if asyncio.iscoroutinefunction(handler):
                    await handler(websocket, exc)
                else:
                    await run_in_threadpool(handler, websocket, exc)

    def http_exception(self, request: Request, exc: HTTPException) -> Response:
        if exc.status_code in {204, 304}:
            return Response(b"", status_code=exc.status_code)
        return PlainTextResponse(exc.detail, status_code=exc.status_code)

    async def websocket_exception(
        self, websocket: WebSocket, exc: WebSocketException
    ) -> None:
        await websocket.close(code=exc.code)

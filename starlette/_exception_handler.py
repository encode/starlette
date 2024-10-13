from __future__ import annotations

import typing
import warnings

from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException, WebSocketException
from starlette.requests import Request
from starlette.types import ASGIApp, ExceptionHandler, Message, Receive, Scope, Send
from starlette.websockets import WebSocket

ExceptionHandlers = typing.Dict[typing.Any, ExceptionHandler]
StatusHandlers = typing.Dict[int, ExceptionHandler]


def _lookup_exception_handler(exc_handlers: ExceptionHandlers, exc: Exception) -> ExceptionHandler | None:
    for cls in type(exc).__mro__:
        if cls in exc_handlers:
            return exc_handlers[cls]
    return None


def wrap_app_handling_exceptions(app: ASGIApp, conn: Request | WebSocket) -> ASGIApp:
    async def wrapped_app(scope: Scope, receive: Receive, send: Send) -> None:
        response_started = False
        websocket_accepted = False
        print("websocket_accepted", websocket_accepted)

        async def sender(message: Message) -> None:
            nonlocal response_started
            nonlocal websocket_accepted

            if message["type"] in ("http.response.start", "websocket.http.response.start"):
                response_started = True
            elif message["type"] == "websocket.accept":
                websocket_accepted = True
            print(f"message: {message}")
            await send(message)

        try:
            await app(scope, receive, sender)
        except Exception as exc:
            exception_handlers: ExceptionHandlers
            status_handlers: StatusHandlers
            try:
                exception_handlers, status_handlers = scope["starlette.exception_handlers"]
            except KeyError:
                exception_handlers, status_handlers = {}, {}

            handler = None
            if isinstance(exc, HTTPException):
                handler = status_handlers.get(exc.status_code)

            if handler is None:
                handler = _lookup_exception_handler(exception_handlers, exc)

            if handler is None:
                raise exc

            if response_started:
                raise RuntimeError("Caught handled exception, but response already started.") from exc

            print("run before the conditional", websocket_accepted)
            if not websocket_accepted and isinstance(exc, WebSocketException):
                warnings.warn("WebSocketException used before the websocket connection was accepted.", UserWarning)

            if is_async_callable(handler):
                response = await handler(conn, exc)
            else:
                response = await run_in_threadpool(handler, conn, exc)  # type: ignore
            if response is not None:
                await response(scope, receive, sender)

    return wrapped_app

import asyncio
import http
import typing

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = None) -> None:
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase
        self.status_code = status_code
        self.detail = detail


class ExceptionMiddleware:
    def __init__(self, app: ASGIApp, debug: bool = False) -> None:
        self.app = app
        self.debug = debug  # TODO: We ought to handle 404 cases if debug is set.
        self._status_handlers = {}  # type: typing.Dict[int, typing.Callable]
        self._exception_handlers = {
            HTTPException: self.http_exception
        }  # type: typing.Dict[typing.Type[Exception], typing.Callable]

    def add_exception_handler(
        self,
        category: typing.Union[int, typing.Type[Exception]],
        handler: typing.Callable,
    ) -> None:
        if isinstance(category, int):
            self._status_handlers[category] = handler
        else:
            assert issubclass(category, Exception)
            self._exception_handlers[category] = handler

    def _lookup_exception_handler(
        self, exc: Exception
    ) -> typing.Optional[typing.Callable]:
        for cls in type(exc).__mro__:
            if cls in self._exception_handlers:
                return self._exception_handlers[cls]
        return None

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] != "http":
            return self.app(scope)

        async def app(receive: Receive, send: Send) -> None:
            response_started = False

            async def sender(message: Message) -> None:
                nonlocal response_started

                if message["type"] == "http.response.start":
                    response_started = True
                await send(message)

            try:
                instance = self.app(scope)
                await instance(receive, sender)
            except Exception as exc:
                handler = None

                if isinstance(exc, HTTPException):
                    handler = self._status_handlers.get(exc.status_code)

                if handler is None:
                    handler = self._lookup_exception_handler(exc)

                if handler is None:
                    raise exc from None

                if response_started:
                    msg = "Caught handled exception, but response already started."
                    raise RuntimeError(msg) from exc

                request = Request(scope, receive=receive)
                if asyncio.iscoroutinefunction(handler):
                    response = await handler(request, exc)
                else:
                    response = await run_in_threadpool(handler, request, exc)
                await response(receive, sender)

        return app

    def http_exception(self, request: Request, exc: HTTPException) -> Response:
        if exc.status_code in {204, 304}:
            return Response(b"", status_code=exc.status_code)
        return PlainTextResponse(exc.detail, status_code=exc.status_code)

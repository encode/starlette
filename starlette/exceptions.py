from starlette.request import Request
from starlette.response import PlainTextResponse
import asyncio
import http


class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase
        self.status_code = status_code
        self.detail = detail


class ExceptionMiddleware:
    def __init__(self, app, exception_handlers=None, error_handler=None):
        self.app = app
        self.exception_handlers = exception_handlers or {}
        self.exception_handlers.setdefault(HTTPException, self.http_exception)
        self.error_handler = error_handler or self.server_error

    def set_error_handler(self, handler):
        self.error_handler = handler

    def add_exception_handler(self, exc_class, handler):
        self.exception_handlers[exc_class] = handler

    def lookup_exception_handler(self, exc):
        for cls in type(exc).__mro__:
            handler = self.exception_handlers.get(cls)
            if handler is not None:
                return handler
        return None

    def __call__(self, scope):
        if scope["type"] != "http":
            return self.app(scope)

        async def app(receive, send):
            response_started = False

            async def sender(message):
                nonlocal response_started

                if message["type"] == "http.response.start":
                    response_started = True
                await send(message)

            try:
                try:
                    instance = self.app(scope)
                    await instance(receive, sender)
                except BaseException as exc:
                    # Exception handling is applied to any registed exception
                    # class or subclass that occurs within the application.
                    handler = self.lookup_exception_handler(exc)
                    if handler is None:
                        # Any unhandled cases get raised to the error handler.
                        raise exc from None

                    if response_started:
                        msg = "Caught handled exception, but response already started."
                        raise RuntimeError(msg) from exc

                    request = Request(scope, receive=receive)
                    if asyncio.iscoroutinefunction(handler):
                        response = await handler(request, exc)
                    else:
                        response = handler(request, exc)
                    await response(receive, sender)

            except BaseException as exc:
                # Error handling is applied to any unhandled exceptions occuring
                # within either the application or within the exception handlers.
                request = Request(scope, receive=receive)
                if asyncio.iscoroutinefunction(self.error_handler):
                    response = await self.error_handler(request, exc)
                else:
                    response = self.error_handler(request, exc)
                if not response_started:
                    await response(receive, send)
                # We always raise the exception up to the server so that it
                # is notified too. Typically this will mean that it'll log
                # the exception.
                raise

        return app

    def http_exception(self, request, exc):
        return PlainTextResponse(exc.detail, status_code=exc.status_code)

    def server_error(self, request, exc):
        return PlainTextResponse("Server Error", status_code=500)

from starlette.request import Request
from starlette.response import PlainTextResponse
import http


class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase
        self.status_code = status_code
        self.detail = detail


class ExceptionMiddleware:
    def __init__(self, app, handlers=None, error_handler=None):
        self.app = app
        self.handlers = handlers or {}
        self.error_handler = error_handler or self.server_error
        self.handlers.setdefault(HTTPException, self.http_exception)

    def __call__(self, scope):
        if scope['type'] != 'http':
            return self.app(scope)

        async def app(receive, send):
            try:
                try:
                    instance = self.app(scope)
                    await instance(receive, send)
                except BaseException as exc:
                    request = Request(scope, receive=receive)
                    for cls, handler in self.handlers.items():
                        if isinstance(exc, cls):
                            response = await handler(request, exc)
                            await response(receive, send)
                            return
                    raise exc from None
            except BaseException as exc:
                request = Request(scope, receive=receive)
                response = await self.error_handler(request, exc)
                await response(receive, send)
                raise
        return app

    async def http_exception(self, request, exc):
        return PlainTextResponse(exc.detail, status_code=exc.status_code)

    async def server_error(self, request, exc):
        return PlainTextResponse("Server Error", status_code=500)

from starlette.request import Request
from starlette.response import Response


def asgi_application(func):
    def app(scope):
        async def awaitable(receive, send):
            request = Request(scope, receive)
            response = func(request)
            assert isinstance(response, Response)
            await response(receive, send)

        return awaitable

    return app

from starlette.request import Request
from starlette.response import Response
from starlette.types import ASGIApp, ASGIInstance, Receive, Send, Scope


class View:
    def __call__(self, scope: Scope, **kwargs) -> ASGIApp:
        return self.dispatch(scope, **kwargs)

    def dispatch(self, scope: Scope, **kwargs) -> ASGIInstance:
        request_method = scope["method"] if scope["method"] != "HEAD" else "GET"
        func = getattr(self, request_method.lower(), None)
        if func is None:
            return Response("Not found", 404, media_type="text/plain")

        async def awaitable(receive: Receive, send: Send) -> None:
            request = Request(scope, receive)
            response = await func(request, **kwargs)
            await response(receive, send)

        return awaitable

import asyncio

from starlette.request import Request
from starlette.types import ASGIApp, ASGIInstance, Receive, Send, Scope


class View:
    def __call__(self, scope: Scope) -> ASGIApp:
        return self.dispatch(scope)

    def dispatch(self, scope: Scope) -> ASGIInstance:
        request_method = scope["method"] if scope["method"] != "HEAD" else "GET"
        func = getattr(self, request_method.lower(), None)
        if func is None:
            raise Exception(
                f"Method {request_method} is not implemented for this view."
            )
        is_coroutine = asyncio.iscoroutinefunction(func)

        async def awaitable(receive: Receive, send: Send) -> None:
            request = Request(scope, receive)
            if is_coroutine:
                response = await func(request)
            else:
                response = func(request)
            await response(receive, send)

        return awaitable

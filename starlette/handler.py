import typing

from requests import request
from starlette.requests import Request
from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.types import Receive, Scope, Send

class RouteHandler:

    def __init__(
        self,
        handler: typing.Callable[[Request], typing.Any],
        middlewares: typing.Optional[typing.Sequence[
            typing.Callable[[Request, typing.Callable[[], typing.Any]], typing.Any]
        ]] = None,
        is_class: typing.Optional[bool] = False,
        is_coroutine: typing.Optional[bool] = False
    ) -> None:

        self.middlewares = middlewares
        self.handler = handler
        self.idx = 0

        self.is_class = is_class
        self.is_coroutine = is_coroutine

        
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.request = Request(scope, receive=receive, send=send)
        self.scope, self.receive, self.send = scope, receive, send
        if self.middlewares is None:
            response = await self.call_handler()
        else:
            self.middleware_count = len(self.middlewares)
            response = await self.call_middleware()

        await response(self.scope, self.receive, self.send)

    async def call_handler(self) -> typing.Any:
        if not self.is_class:
            if self.is_coroutine:
                response = await self.handler(self.request)
            else:
                response = await run_in_threadpool(self.handler, self.request)
        else:
            assert self.scope["type"] == "http"
            response = await self.handler(request)
        return response


    async def call_middleware(self):
        if self.middleware_count <= self.idx:
            return await self.call_handler()
        
        
        async def next():
            self.idx += 1
            return await self.call_middleware()
        
        mid = self.middlewares[self.idx]
        if is_async_callable(mid):
            response = await mid(self.request, next)
        else:
            response = await run_in_threadpool(mid, self.request, next)
        return response
            


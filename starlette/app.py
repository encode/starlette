from starlette.request import Request
from starlette.routing import Router, Path
from starlette.types import ASGIInstance, Receive, Scope, Send
from starlette.websockets import WebSocketSession
import asyncio


def request_response(func):
    is_coroutine = asyncio.iscoroutinefunction(func)

    def app(scope: Scope) -> ASGIInstance:
        async def awaitable(receive: Receive, send: Send) -> None:
            request = Request(scope, receive=receive)
            if is_coroutine:
                response = await func(request)
            else:
                response = func(request)
            await response(receive, send)

        return awaitable

    return app


def websocket_session(func):
    def app(scope: Scope) -> ASGIInstance:
        async def awaitable(receive: Receive, send: Send) -> None:
            session = WebSocketSession(scope, receive=receive, send=send)
            await func(session)

        return awaitable

    return app


class App:
    def __init__(self) -> None:
        self.router = Router(routes=[])

    def add_route(self, path: str, route) -> None:
        instance = Path(path, request_response(route))
        self.router.routes.append(instance)

    def add_websocket_route(self, path: str, route) -> None:
        instance = Path(path, websocket_session(route))
        self.router.routes.append(instance)

    def route(self, path: str):
        def decorator(func):
            self.add_route(path, func)
        return decorator

    def websocket_route(self, path: str):
        def decorator(func):
            self.add_websocket_route(path, func)
        return decorator

    def __call__(self, scope: Scope) -> ASGIInstance:
        return self.router(scope)

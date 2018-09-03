from starlette.exceptions import ExceptionMiddleware
from starlette.request import Request
from starlette.routing import Path, PathPrefix, Router
from starlette.types import ASGIApp, ASGIInstance, Receive, Scope, Send
from starlette.websockets import WebSocketSession
import asyncio
import inspect


def request_response(func):
    """
    Takes a function or coroutine `func(request, **kwargs) -> response`,
    and returns an ASGI application.
    """
    is_coroutine = asyncio.iscoroutinefunction(func)

    def app(scope: Scope) -> ASGIInstance:
        async def awaitable(receive: Receive, send: Send) -> None:
            request = Request(scope, receive=receive)
            kwargs = scope.get("kwargs", {})
            if is_coroutine:
                response = await func(request, **kwargs)
            else:
                response = func(request, **kwargs)
            await response(receive, send)

        return awaitable

    return app


def websocket_session(func):
    """
    Takes a coroutine `func(session, **kwargs)`, and returns an ASGI application.
    """

    def app(scope: Scope) -> ASGIInstance:
        async def awaitable(receive: Receive, send: Send) -> None:
            session = WebSocketSession(scope, receive=receive, send=send)
            kwargs = scope.get("kwargs", {})
            await func(session, **kwargs)

        return awaitable

    return app


class App:
    def __init__(self) -> None:
        self.router = Router(routes=[])
        self.exception_middleware = ExceptionMiddleware(self.router)

    def mount(self, path: str, app: ASGIApp):
        prefix = PathPrefix(path, app=app)
        self.router.routes.append(prefix)

    def set_error_handler(self, handler) -> None:
        self.exception_middleware.set_error_handler(handler)

    def add_exception_handler(self, exc_class: type, handler) -> None:
        self.exception_middleware.add_handler(exc_class, handler)

    def add_route(self, path: str, route, methods=None) -> None:
        if not inspect.isclass(route):
            route = request_response(route)
            if methods is None:
                methods = ["GET"]

        instance = Path(path, route, protocol="http", methods=methods)
        self.router.routes.append(instance)

    def add_websocket_route(self, path: str, route) -> None:
        if not inspect.isclass(route):
            route = websocket_session(route)

        instance = Path(path, route, protocol="websocket")
        self.router.routes.append(instance)

    def error_handler(self):
        def decorator(func):
            self.set_error_handler(func)
            return func

        return decorator

    def exception_handler(self, exc_class: type):
        def decorator(func):
            self.add_exception_handler(exc_class, func)
            return func

        return decorator

    def route(self, path: str):
        def decorator(func):
            self.add_route(path, func)
            return func

        return decorator

    def websocket_route(self, path: str):
        def decorator(func):
            self.add_websocket_route(path, func)
            return func

        return decorator

    def __call__(self, scope: Scope) -> ASGIInstance:
        return self.exception_middleware(scope)

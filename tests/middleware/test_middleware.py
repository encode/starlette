from starlette.middleware import Middleware
from starlette.types import Receive, Scope, Send


class CustomMiddleware:
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        return None  # pragma: no cover


def test_middleware_repr():
    middleware = Middleware(CustomMiddleware)
    assert repr(middleware) == "Middleware(CustomMiddleware)"

from starlette.middleware import Middleware
from starlette.types import ASGIApp


class CustomMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app  # pragma: no cover


def test_middleware_repr():
    middleware = Middleware(CustomMiddleware)
    assert repr(middleware) == "Middleware(CustomMiddleware)"

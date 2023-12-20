from starlette.middleware import Middleware
from starlette.types import ASGIApp


class CustomMiddleware:
    def __init__(self, app: ASGIApp, foo: str, *, bar: int) -> None:  # pragma: no cover
        self.app = app
        self.foo = foo
        self.bar = bar


def test_middleware_repr():
    middleware = Middleware(CustomMiddleware, "foo", bar=123)
    assert repr(middleware) == "Middleware(CustomMiddleware, 'foo', bar=123)"


def test_middleware_iter():
    cls, args, kwargs = Middleware(CustomMiddleware, "foo", bar=123)
    assert (cls, args, kwargs) == (CustomMiddleware, ("foo",), {"bar": 123})

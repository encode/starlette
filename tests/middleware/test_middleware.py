from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send


class CustomMiddleware:  # pragma: no cover
    def __init__(self, app: ASGIApp, foo: str, *, bar: int) -> None:
        self.app = app
        self.foo = foo
        self.bar = bar

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class TestMiddleware:
    custom_middleware = Middleware(CustomMiddleware, "foo", bar=123, baz="custom")

    def test_created_instance(self) -> None:
        custom_middleware = self.custom_middleware
        assert isinstance(custom_middleware, Middleware)
        assert custom_middleware.cls == CustomMiddleware  # type: ignore

    def test_repr(self) -> None:
        custom_middleware = self.custom_middleware
        assert repr(custom_middleware) == "Middleware(CustomMiddleware, 'foo', bar=123, baz='custom')"

    def test_iter(self) -> None:
        custom_middleware = self.custom_middleware
        cls, args, kwargs = custom_middleware
        assert cls == custom_middleware.cls
        assert args == ("foo",)
        assert kwargs == {"bar": 123, "baz": "custom"}

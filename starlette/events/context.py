import typing
from typing import TypeVar

from starlette._utils import is_async_callable
from starlette.types import Receive, Scope, Send

_T = TypeVar("_T")


class AyncLifespanContextManager:
    """
    Bridges the on_startup/on_shutdown to the new async context manager.
    """

    def __init__(
        self,
        on_startup: typing.Optional[typing.Sequence[typing.Callable]] = None,
        on_shutdown: typing.Optional[typing.Sequence[typing.Callable]] = None,
    ) -> None:
        self.on_startup = [] if on_startup is None else list(on_startup)
        self.on_shutdown = [] if on_shutdown is None else list(on_shutdown)

    def __call__(self: _T, app: object) -> _T:
        return self

    async def __aenter__(self):
        for handler in self.on_startup:
            if is_async_callable(handler):
                await handler()
            else:
                handler()

    async def __aexit__(
        self, scope: Scope, receive: Receive, send: Send, **kwargs: typing.Any
    ):
        for handler in self.on_shutdown:
            if is_async_callable(handler):
                await handler()
            else:
                handler()

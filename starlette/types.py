import sys
import typing

if sys.version_info < (3, 8):  # pragma: no cover
    from typing_extensions import Protocol
else:  # pragma: no cover
    from typing import Protocol

AppType = typing.TypeVar("AppType")

Scope = typing.MutableMapping[str, typing.Any]
Message = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]

ASGIApp = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]

StatelessLifespan = typing.Callable[[AppType], typing.AsyncContextManager[None]]
StatefulLifespan = typing.Callable[
    [AppType], typing.AsyncContextManager[typing.Mapping[str, typing.Any]]
]
Lifespan = typing.Union[StatelessLifespan[AppType], StatefulLifespan[AppType]]


# This callable protocol can both be used to represent a function returning
# an ASGIApp, or a class with an __init__ method matching this __call__ signature
# and a __call__ method matching the ASGIApp signature.
class MiddlewareType(Protocol):
    __name__: str

    def __call__(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> ASGIApp:  # pragma: no cover
        ...

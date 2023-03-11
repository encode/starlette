import typing

T = typing.TypeVar("T")

Scope = typing.MutableMapping[str, typing.Any]
Message = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]

ASGIApp = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]

StatelessLifespan = typing.Callable[[T], typing.AsyncContextManager[None]]
StatefulLifespan = typing.Callable[
    [T], typing.AsyncContextManager[typing.Mapping[str, typing.Any]]
]
Lifespan = typing.Union[StatelessLifespan[T], StatefulLifespan[T]]

import typing
import warnings

warnings.warn(
    f"'{__name__}' is deprecated. Import types from 'asgiref.typing' instead.",
    category=DeprecationWarning,
    stacklevel=2,
)


HTTPScope = typing.MutableMapping[str, typing.Any]
LifespanScope = typing.MutableMapping[str, typing.Any]
WebSocketScope = typing.MutableMapping[str, typing.Any]
WWWScope = typing.Union[HTTPScope, WebSocketScope]
Scope = typing.Union[HTTPScope, LifespanScope, WebSocketScope]

Message = typing.MutableMapping[str, typing.Any]
ASGISendEvent = typing.MutableMapping[str, typing.Any]
ASGIReceiveEvent = typing.MutableMapping[str, typing.Any]
WebSocketSendEvent = typing.MutableMapping[str, typing.Any]
WebSocketReceiveEvent = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[ASGIReceiveEvent]]
ASGIReceiveCallable = typing.Callable[[], typing.Awaitable[ASGIReceiveEvent]]

Send = typing.Callable[[ASGISendEvent], typing.Awaitable[None]]
ASGISendCallable = typing.Callable[[ASGISendEvent], typing.Awaitable[None]]

ASGIApp = typing.Callable[
    [Scope, ASGIReceiveCallable, ASGISendCallable], typing.Awaitable[None]
]
ASGI3Application = typing.Callable[
    [Scope, ASGIReceiveCallable, ASGISendCallable], typing.Awaitable[None]
]

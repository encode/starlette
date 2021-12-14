import typing

Scope = typing.MutableMapping[str, typing.Any]

Message = typing.MutableMapping[str, typing.Any]
ASGISendEvent = typing.MutableMapping[str, typing.Any]
ASGIReceiveEvent = typing.MutableMapping[str, typing.Any]
WebSocketSendEvent = typing.MutableMapping[str, typing.Any]
WebSocketReceiveEvent = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[ASGIReceiveEvent]]
Send = typing.Callable[[ASGISendEvent], typing.Awaitable[None]]

ASGIApp = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]
ASGI3Application = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]

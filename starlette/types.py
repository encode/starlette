import sys
import typing

from starlette.requests import Request
from starlette.responses import Response

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol

if sys.version_info >= (3, 9):
    from collections.abc import Mapping
else:
    from typing import Mapping


Scope = typing.MutableMapping[str, typing.Any]
Message = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]

ASGIApp = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]


class ExceptionHandler(Protocol):
    def __call__(self, __request: Request, __exc: Exception) -> Response:
        ...


class AsyncExceptionHandler(Protocol):
    async def __call__(self, __request: Request, __exc: Exception) -> Response:
        ...


ExceptionHandlers = Mapping[
    typing.Union[int, typing.Type[Exception]],
    typing.Union[ExceptionHandler, AsyncExceptionHandler],
]

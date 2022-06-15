from typing import AsyncGenerator, Callable, Optional, Union

from .._compat import aclosing
from ..datastructures import MutableHeaders
from ..requests import HTTPConnection
from ..responses import Response
from ..types import ASGIApp, Message, Receive, Scope, Send

_DispatchFlow = Union[
    # Default case:
    # response = yield
    AsyncGenerator[None, Response],
    # Early response and/or error handling:
    # if condition:
    #     yield Response(...)
    #     return
    # try:
    #     response = yield None
    # except Exception:
    #     yield Response(...)
    # else:
    #    ...
    AsyncGenerator[Optional[Response], Response],
]


class HTTPMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        dispatch: Optional[Callable[[HTTPConnection], _DispatchFlow]] = None,
    ) -> None:
        if dispatch is None:
            dispatch = self.dispatch

        self.app = app
        self._dispatch_func = dispatch

    def dispatch(self, __conn: HTTPConnection) -> _DispatchFlow:
        raise NotImplementedError  # pragma: no cover

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        conn = HTTPConnection(scope)

        async with aclosing(self._dispatch_func(conn)) as flow:
            # Kick the flow until the first `yield`.
            # Might respond early before we call into the app.
            maybe_early_response = await flow.__anext__()

            if maybe_early_response is not None:
                try:
                    await flow.__anext__()
                except StopAsyncIteration:
                    pass
                else:
                    raise RuntimeError("dispatch() should yield exactly once")

                await maybe_early_response(scope, receive, send)
                return

            response_started: set = set()

            async def wrapped_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    response_started.add(True)

                    response = Response(status_code=message["status"])
                    response.raw_headers.clear()

                    try:
                        await flow.asend(response)
                    except StopAsyncIteration:
                        pass
                    else:
                        raise RuntimeError("dispatch() should yield exactly once")

                    headers = MutableHeaders(raw=message["headers"])
                    headers.update(response.headers)

                await send(message)

            try:
                await self.app(scope, receive, wrapped_send)
            except Exception as exc:
                if response_started:
                    raise

                try:
                    response = await flow.athrow(exc)
                except StopAsyncIteration:
                    response = None
                except Exception:
                    # Exception was not handled, or they raised another one.
                    raise

                if response is None:
                    raise RuntimeError(
                        f"dispatch() handled exception {exc!r}, "
                        "but no response was returned"
                    )

                await response(scope, receive, send)
                return

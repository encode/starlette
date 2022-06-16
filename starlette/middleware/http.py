from typing import AsyncGenerator, Callable, Optional, Union

from .._compat import aclosing
from ..datastructures import MutableHeaders
from ..requests import HTTPConnection
from ..responses import Response
from ..types import ASGIApp, Message, Receive, Scope, Send

# This type hint not exposed, as it exists mostly for our own documentation purposes.
# End users should use one of these type hints explicitly when overriding '.dispatch()'.
_DispatchFlow = Union[
    # Default case:
    #   response = yield
    AsyncGenerator[None, Response],
    # Early response and/or error handling:
    #   if condition:
    #       yield Response(...)
    #       return
    #   try:
    #       response = yield None
    #   except Exception:
    #       yield Response(...)
    #   else:
    #       ...
    AsyncGenerator[Optional[Response], Response],
]


class HTTPMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        dispatch: Optional[Callable[[HTTPConnection], _DispatchFlow]] = None,
    ) -> None:
        self.app = app
        self._dispatch_func = self.dispatch if dispatch is None else dispatch

    def dispatch(self, __conn: HTTPConnection) -> _DispatchFlow:
        raise NotImplementedError(
            "No dispatch implementation was given. "
            "Either pass 'dispatch=...' to HTTPMiddleware, "
            "or subclass HTTPMiddleware and override the 'dispatch()' method."
        )

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

            response_started = False
            response_finished = False

            async def wrapped_send(message: Message) -> None:
                nonlocal response_started, response_finished

                if message["type"] == "http.response.start":
                    response_started = True

                    response = Response(status_code=message["status"])
                    response.raw_headers.clear()

                    try:
                        new_response = await flow.asend(response)
                    except StopAsyncIteration:
                        pass
                    else:
                        if new_response is None:
                            raise RuntimeError("dispatch() should yield exactly once")
                        try:
                            await flow.__anext__()
                        except StopAsyncIteration:
                            pass
                        else:
                            raise RuntimeError("dispatch() should yield exactly once")
                        await new_response(scope, receive, send)
                        response_finished = True
                        return
                    headers = MutableHeaders(raw=message["headers"])
                    headers.update(response.headers)
                    message["headers"] = headers.raw

                if not response_finished:
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

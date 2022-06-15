from contextlib import AsyncExitStack
from typing import AsyncGenerator, AsyncIterable, Callable, Optional, Union

from .._compat import aclosing
from ..datastructures import MutableHeaders
from ..requests import HTTPConnection
from ..responses import Response, StreamingResponse
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

        async with AsyncExitStack() as stack:
            flow = await stack.enter_async_context(aclosing(self._dispatch_func(conn)))

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

            async def _wrapped_send() -> AsyncGenerator[None, Optional[Message]]:
                nonlocal response_started

                message = yield
                assert message is not None
                assert message["type"] == "http.response.start"
                response_started = True
                sent_start_response = False
                start_message = message

                async def ensure_start_response() -> None:
                    if not sent_start_response:
                        await send(start_message)
                
                stack.push_async_callback(ensure_start_response)

                message = yield
                assert message is not None
                assert message["type"] == "http.response.body"
                headers = MutableHeaders(raw=start_message["headers"])
                if message.get("more_body", False) is False:
                    response = Response(
                        status_code=start_message["status"],
                        headers=headers,
                        content=message.get("body", b""),
                    )
                else:
                    async def _resp_stream() -> AsyncGenerator[bytes, None]:
                        raise NotImplementedError
                        yield

                    resp_stream = await stack.enter_async_context(aclosing(_resp_stream()))
                    response = StreamingResponse(
                        content=resp_stream,
                        status_code=start_message["status"],
                        headers=headers,
                    )
                try:
                    await flow.asend(response)
                except StopAsyncIteration:
                    pass
                else:
                    raise RuntimeError("dispatch() should yield exactly once")
                start_message["headers"] = response.headers.raw
                await send(start_message)
                sent_start_response = True
                await send(message)

                while True:
                    message = yield
                    assert message is not None
                    await send(message)

            wrapped_send = await stack.enter_async_context(aclosing(_wrapped_send()))
            await wrapped_send.asend(None)

            try:
                await self.app(scope, receive, wrapped_send.asend)
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

from functools import partial
from typing import AsyncGenerator, Callable, Optional

from .._compat import aclosing
from ..datastructures import MutableHeaders
from ..responses import Response
from ..types import ASGIApp, Message, Receive, Scope, Send

HTTPDispatchFlow = AsyncGenerator[Optional[Response], Response]


class HTTPMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        dispatch_func: Optional[Callable[[Scope], HTTPDispatchFlow]] = None,
    ) -> None:
        self.app = app
        self.dispatch_func = self.dispatch if dispatch_func is None else dispatch_func

    def dispatch(self, scope: Scope) -> HTTPDispatchFlow:
        raise NotImplementedError  # pragma: no cover

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async with aclosing(self.dispatch(scope)) as flow:
            # Kick the flow until the first `yield`.
            # Might respond early before we call into the app.
            early_response = await flow.__anext__()

            if early_response is not None:
                await early_response(scope, receive, send)
                return

            response_started = set[bool]()

            wrapped_send = partial(
                self._send,
                flow=flow,
                response_started=response_started,
                send=send,
            )

            try:
                await self.app(scope, receive, wrapped_send)
            except Exception as exc:
                if response_started:
                    raise

                try:
                    response = await flow.athrow(exc)
                except Exception:
                    # Exception was not handled, or they raised another one.
                    raise

                if response is None:
                    raise RuntimeError(
                        f"dispatch() handled exception {exc!r}, "
                        "but no response was returned"
                    )

                await response(scope, receive, send)

            if not response_started:
                raise RuntimeError("No response returned.")

    async def _send(
        self,
        message: Message,
        *,
        flow: HTTPDispatchFlow,
        response_started: set,
        send: Send,
    ) -> None:
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

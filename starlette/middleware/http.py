from functools import partial
from typing import Generator, Optional
from ..types import ASGIApp, Scope, Receive, Send, Message
from ..responses import Response
from ..datastructures import MutableHeaders


class HTTPMiddleware:
    DispatchFlow = Generator[Optional[Response], Response, None]

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def dispatch(self, scope: Scope) -> DispatchFlow:
        raise NotImplementedError

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        flow = self.dispatch(scope)

        try:
            # Run until first `yield` to allow modifying the connection scope.
            # Middleware may return a response before we call into the underlying app.
            early_response = flow.__next__()
        except StopIteration:
            raise RuntimeError("dispatch() did not run")

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
            try:
                response = flow.throw(exc)
            except Exception:
                # Exception was not handled, or they raised another one.
                raise

            if response is None:
                raise RuntimeError(
                    f"dispatch() handled exception {exc!r}, "
                    "but no response application was returned"
                )

            await response(scope, receive, send)

        if not response_started:
            raise RuntimeError("No response returned.")

    async def _send(
        self, message: Message, *, flow: DispatchFlow, response_started: set, send: Send
    ) -> None:
        if message["type"] == "http.response.start":
            response_started.add(True)

            response = Response(status_code=message["status"])
            response.raw_headers.clear()

            try:
                flow.send(response)
            except StopIteration as exc:
                if exc.value is not None:
                    raise RuntimeError("swapping responses it not supported")
            else:
                raise RuntimeError("dispatch() should yield exactly once")

            headers = MutableHeaders(raw=message["headers"])
            headers.update(response.headers)

        await send(message)

from typing import Any, AsyncGenerator, Callable, Optional, Union

from .._compat import aclosing
from ..datastructures import Headers
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

            async def wrapped_send(message: Message) -> None:
                nonlocal response_started

                if message["type"] == "http.response.start":
                    response_started = True

                    headers = Headers(raw=message["headers"])
                    response = _StubResponse(
                        status_code=message["status"],
                        media_type=headers.get("content-type"),
                    )
                    response.raw_headers = headers.raw

                    try:
                        await flow.asend(response)
                    except StopAsyncIteration:
                        pass
                    else:
                        raise RuntimeError("dispatch() should yield exactly once")

                    message["headers"] = response.raw_headers

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


# This customized stub response helps prevent users from shooting themselves
# in the foot, doing things that don't actually have any effect.


class _StubResponse(Response):
    def __init__(self, status_code: int, media_type: Optional[str] = None) -> None:
        self._status_code = status_code
        self._media_type = media_type
        self.raw_headers = []

    @property  # type: ignore
    def status_code(self) -> int:  # type: ignore
        return self._status_code

    @status_code.setter
    def status_code(self, value: Any) -> None:
        raise RuntimeError(
            "Setting .status_code in HTTPMiddleware is not supported. "
            "If you're writing middleware that requires modifying the response "
            "status code or sending another response altogether, please consider "
            "writing pure ASGI middleware. "
            "See: https://starlette.io/middleware/#pure-asgi-middleware"
        )

    @property  # type: ignore
    def media_type(self) -> Optional[str]:  # type: ignore
        return self._media_type

    @media_type.setter
    def media_type(self, value: Any) -> None:
        raise RuntimeError(
            "Setting .media_type in HTTPMiddleware is not supported, as it has "
            "no effect. If you do need to tweak the response "
            "content type, consider: response.headers['Content-Type'] = ..."
        )

    @property  # type: ignore
    def body(self) -> bytes:  # type: ignore
        raise RuntimeError(
            "Accessing the response body in HTTPMiddleware is not supported. "
            "If you're writing middleware that requires peeking into the response "
            "body, please consider writing pure ASGI middleware and wrapping send(). "
            "See: https://starlette.io/middleware/#pure-asgi-middleware"
        )

    @body.setter
    def body(self, body: bytes) -> None:
        raise RuntimeError(
            "Setting the response body in HTTPMiddleware is not supported."
            "If you're writing middleware that requires modifying the response "
            "body, please consider writing pure ASGI middleware and wrapping send(). "
            "See: https://starlette.io/middleware/#pure-asgi-middleware"
        )

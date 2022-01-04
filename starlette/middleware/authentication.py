import typing

from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    WebSocketCloseEvent,
    WWWScope,
)

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    UnauthenticatedUser,
)
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse, Response


class AuthenticationMiddleware:
    def __init__(
        self,
        app: ASGI3Application,
        backend: AuthenticationBackend,
        on_error: typing.Callable[
            [HTTPConnection, AuthenticationError], Response
        ] = None,
    ) -> None:
        self.app = app
        self.backend = backend
        self.on_error: typing.Callable[
            [HTTPConnection, AuthenticationError], Response
        ] = (on_error if on_error is not None else self.default_on_error)

    async def __call__(
        self, scope: WWWScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        if scope["type"] not in ["http", "websocket"]:
            await self.app(scope, receive, send)
            return

        conn = HTTPConnection(scope)
        try:
            auth_result = await self.backend.authenticate(conn)
        except AuthenticationError as exc:
            response = self.on_error(conn, exc)
            if scope["type"] == "websocket":
                close_event = WebSocketCloseEvent(
                    type="websocket.close", code=1000, reason=None
                )
                await send(close_event)
            else:
                await response(scope, receive, send)
            return

        if auth_result is None:
            auth_result = AuthCredentials(), UnauthenticatedUser()
        scope["auth"], scope["user"] = auth_result  # type: ignore[index,typeddict-item]
        await self.app(scope, receive, send)

    @staticmethod
    def default_on_error(conn: HTTPConnection, exc: Exception) -> Response:
        return PlainTextResponse(str(exc), status_code=400)

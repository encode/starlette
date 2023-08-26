import typing
from datetime import datetime, timezone

import jwt
from jwt.exceptions import InvalidTokenError

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class JwtSessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        key: typing.Union[str, Secret],
        algorithm: str = "HS256",
        session_cookie: str = "session",
        path: str = "/",
        same_site: typing.Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
    ) -> None:
        self.app = app
        self.key = key
        self.algorithm = algorithm
        self.session_cookie = session_cookie
        self.path = path
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"

    def encode(self, claims: typing.Dict[str, typing.Any]) -> str:
        return str(jwt.encode(claims, key=self.key, algorithm=self.algorithm))

    def decode(self, token: str) -> typing.Dict[str, typing.Any]:
        return dict(jwt.decode(token, key=self.key, algorithms=[self.algorithm]))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie]
            try:
                scope["session"] = self.decode(data)
                initial_session_was_empty = False
            except InvalidTokenError:
                scope["session"] = {}
        else:
            scope["session"] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                if scope["session"]:
                    # We have session data to persist.
                    claims = dict(scope["session"])
                    max_age = ""
                    if "exp" in claims:
                        difference = datetime.fromtimestamp(
                            claims["exp"], tz=timezone.utc
                        ) - datetime.now(tz=timezone.utc)
                        max_age = (
                            f"Max-Age={max(round(difference.total_seconds()), 0)}; "
                        )

                    data = self.encode(claims)
                    headers = MutableHeaders(scope=message)
                    header_value = "{session_cookie}={data}; path={path}; {max_age}{security_flags}".format(  # noqa E501
                        session_cookie=self.session_cookie,
                        data=data,
                        path=self.path,
                        max_age=max_age,
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif not initial_session_was_empty:
                    # The session has been cleared.
                    headers = MutableHeaders(scope=message)
                    header_value = "{session_cookie}={data}; path={path}; {expires}{security_flags}".format(  # noqa E501
                        session_cookie=self.session_cookie,
                        data="null",
                        path=self.path,
                        expires="expires=Thu, 01 Jan 1970 00:00:00 GMT; ",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)

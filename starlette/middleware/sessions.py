import json
import typing
from base64 import b64decode, b64encode

import itsdangerous
from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    ASGISendEvent,
    WWWScope,
)
from itsdangerous.exc import BadSignature

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection


class SessionMiddleware:
    def __init__(
        self,
        app: ASGI3Application,
        secret_key: typing.Union[str, Secret],
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 60 * 60,  # 14 days, in seconds
        same_site: str = "lax",
        https_only: bool = False,
    ) -> None:
        self.app = app
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"

    async def __call__(
        self, scope: WWWScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie].encode("utf-8")
            try:
                data = self.signer.unsign(data, max_age=self.max_age)
                scope["session"] = json.loads(b64decode(data))  # type: ignore[index]
                initial_session_was_empty = False
            except BadSignature:
                scope["session"] = {}  # type: ignore[index]
        else:
            scope["session"] = {}  # type: ignore[index]

        async def send_wrapper(message: ASGISendEvent) -> None:
            if message["type"] == "http.response.start":
                path = scope.get("root_path", "") or "/"
                if scope.get("session"):
                    # We have session data to persist.
                    scope_session = scope["session"]  # type: ignore[typeddict-item]
                    data = b64encode(json.dumps(scope_session).encode("utf-8"))
                    data = self.signer.sign(data)
                    headers = MutableHeaders(scope=message)
                    header_value = "%s=%s; path=%s; Max-Age=%d; %s" % (
                        self.session_cookie,
                        data.decode("utf-8"),
                        path,
                        self.max_age,
                        self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif not initial_session_was_empty:
                    # The session has been cleared.
                    headers = MutableHeaders(scope=message)
                    header_value = "{}={}; {}".format(
                        self.session_cookie,
                        f"null; path={path}; expires=Thu, 01 Jan 1970 00:00:00 GMT;",
                        self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)

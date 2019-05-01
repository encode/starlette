import json
import typing
from base64 import b64decode, b64encode

import itsdangerous
from itsdangerous.exc import BadTimeSignature, SignatureExpired

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection, Request
from starlette.sessions import CookieBackend, SessionBackend, SessionNotFoundError
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        secret_key: typing.Union[str, Secret],
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 60 * 60,  # 14 days, in seconds
        same_site: str = "lax",
        https_only: bool = False,
        backend: SessionBackend = None,
    ) -> None:
        self.app = app
        self.backend = backend or CookieBackend()
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        session_id = None
        if self.session_cookie in connection.cookies:
            try:
                session_id = connection.cookies[self.session_cookie]
                signed_data = await self.backend.read(session_id)
                if signed_data is None:  # there is no data for key
                    raise SessionNotFoundError()

                data = self.signer.unsign(signed_data, max_age=self.max_age)
                scope["session"] = json.loads(b64decode(data))
                initial_session_was_empty = False
            except (BadTimeSignature, SignatureExpired, SessionNotFoundError):
                scope["session"] = {}
        else:
            scope["session"] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                if scope["session"]:
                    # We have session data to persist.
                    nonlocal session_id
                    if not session_id:
                        session_id = self.backend.generate_id()

                    data = b64encode(json.dumps(scope["session"]).encode("utf-8"))
                    session_id = await self.backend.write(
                        session_id, self.signer.sign(data).decode("utf-8")
                    )
                    headers = MutableHeaders(scope=message)
                    header_value = "%s=%s; path=/; Max-Age=%d; %s" % (
                        self.session_cookie,
                        session_id,
                        self.max_age,
                        self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif not initial_session_was_empty:
                    # The session has been cleared.
                    headers = MutableHeaders(scope=message)
                    header_value = "%s=%s; %s" % (
                        self.session_cookie,
                        "null; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT;",
                        self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)

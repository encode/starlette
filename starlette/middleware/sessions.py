import json
import typing
from datetime import datetime, timedelta, timezone
from base64 import b64decode, b64encode

import itsdangerous
from itsdangerous.exc import BadSignature, SignatureExpired

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        secret_key: typing.Union[str, Secret],
        session_cookie: str = "session",
        max_age: typing.Optional[int] = 14 * 24 * 60 * 60,  # 14 days, in seconds
        path: str = "/",
        same_site: typing.Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
        persist_session: bool = False,
        auto_refresh_window: int = 0, # seconds, default 0 to not auto refresh, 240 seconds for 4 minute window to refresh
        domain: typing.Optional[str] = None,
    ) -> None:
        self.app = app
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.security_flags = "httponly; samesite=" + same_site
        self.persist_session = persist_session
        self.auto_refresh_window = auto_refresh_window
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"
        if domain is not None:
            self.security_flags += f"; domain={domain}"

    def decodeCookie(self,cookie):
        result = {}
        try:
            data = self.signer.unsign(cookie, max_age=self.max_age,return_timestamp=True)
            result["datetime"] = data[1]
            result["session"] = json.loads(b64decode(data[0]))
        except (BadSignature, SignatureExpired):
            result = {}
        return result
        
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        inject_session = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie].encode("utf-8")
            data = self.decodeCookie(data)
            scope["session"] = data["session"]
            session_exp = data["datetime"] + timedelta(seconds=self.max_age)
            now = datetime.now(timezone.utc)
            if self.auto_refresh_window:
                if now >= (session_exp - timedelta(seconds=self.auto_refresh_window)) and now <= session_exp:
                    #Session needs refreshing
                    inject_session = True
                else:
                    #Session does not need to be refreshed
                    inject_session = False
            elif self.persist_session:
                #Sessions are not auto refresed, has an existing session. Catch statement should catch it if its expired.
                inject_session = False
        else:
            scope["session"] = {}


        async def send_wrapper(message: Message) -> None:
            changed = False
            if message["type"] == "http.response.start":
                if self.session_cookie in connection.cookies:
                    old_data = self.decodeCookie(connection.cookies[self.session_cookie].encode("utf-8"))
                    if old_data["session"] != scope["session"]:
                        #Scope has different data, old_data is from the cookie. If they don't match then update.
                        changed = True 
                if scope["session"] and (inject_session or changed):
                    # We have data that needs to be persisted or refreshed. Don't inject a session if no session exists.
                    data = b64encode(json.dumps(scope["session"]).encode("utf-8"))
                    data = self.signer.sign(data)
                    headers = MutableHeaders(scope=message)
                    header_value = "{session_cookie}={data}; path={path}; {max_age}{security_flags}".format(  # noqa E501
                        session_cookie=self.session_cookie,
                        data=data.decode("utf-8"),
                        path=self.path,
                        max_age=f"Max-Age={self.max_age}; " if self.max_age else "",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif not inject_session and not scope["session"]:
                    # The session is cleared. BadSignature or initial_session_was_empty
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
        

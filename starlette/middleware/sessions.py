import typing

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection
from starlette.sessions import CookieBackend, Session, SessionBackend
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
        autoload: bool = False,
    ) -> None:
        self.app = app
        self.backend = backend or CookieBackend(secret_key, max_age)
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.security_flags = "httponly; samesite=" + same_site
        self.autoload = autoload
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        session_id = connection.cookies.get(self.session_cookie, None)

        session = Session(self.backend, session_id)
        if self.autoload:
            await session.load()
        scope["session"] = session

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                path = scope.get("root_path", "") or "/"
                if session.is_modified:
                    # We have session data to persist (data was changed, cleared, etc).
                    nonlocal session_id
                    session_id = await session.persist()

                    headers = MutableHeaders(scope=message)
                    header_value = "%s=%s; path=%s; Max-Age=%d; %s" % (
                        self.session_cookie,
                        session_id,
                        path,
                        self.max_age,
                        self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif session.is_loaded and session.is_empty:
                    # no interactions to session were done
                    headers = MutableHeaders(scope=message)
                    header_value = "{}={}; {}".format(
                        self.session_cookie,
                        f"null; path={path}; expires=Thu, 01 Jan 1970 00:00:00 GMT;",
                        self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)

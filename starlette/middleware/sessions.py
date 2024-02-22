import json
import typing
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone

import itsdangerous
from itsdangerous.exc import BadSignature, SignatureExpired

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send


# mutable mapping that keeps track of whether it has been modified
class ModifiedDict(typing.Dict[str, typing.Any]):
    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        self.modify = False
        self.invalid = False

    def __setitem__(self, key: str, value: typing.Any) -> None:  # pragma: no cover
        super().__setitem__(key, value)
        self.modify = True

    def __delitem__(self, key: str) -> None:  # pragma: no cover
        super().__delitem__(key)
        self.modify = True

    def clear(self) -> None:
        super().clear()
        self.invalid = True
        self.modify = True

    def pop(
        self, key: str, default: typing.Any = None
    ) -> typing.Any:  # pragma: no cover
        value = super().pop(key, default)
        self.modify = True
        return value

    def popitem(self) -> typing.Any:  # pragma: no cover
        value = super().popitem()
        self.modify = True
        return value

    def setdefault(
        self, key: str, default: typing.Any = None
    ) -> typing.Any:  # pragma: no cover
        value = super().setdefault(key, default)
        self.modify = True
        return value

    def update(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().update(*args, **kwargs)
        self.modify = True


class SessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        secret_key: typing.Union[str, Secret],
        session_cookie: str = "session",
        max_age: typing.Optional[int] = 14 * 24 * 60 * 60,  # 14 days, in seconds
        refresh_window: typing.Optional[int] = None,
        path: str = "/",
        same_site: typing.Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
        domain: typing.Optional[str] = None,
        partitioned: typing.Optional[bool] = False,
    ) -> None:
        self.app = app
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.refresh_window = refresh_window
        self.path = path
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"
        if domain is not None:
            self.security_flags += f"; domain={domain}"
        if partitioned:
            self.security_flags += "; partitioned"

    # Decode and validate cookie
    def decode_cookie(self, cookie: bytes) -> ModifiedDict:
        result: ModifiedDict = ModifiedDict()
        try:
            data = self.signer.unsign(
                cookie, max_age=self.max_age, return_timestamp=True
            )
            result = ModifiedDict(json.loads(b64decode(data[0])))
        except (BadSignature, SignatureExpired):
            result.invalid = True
            return result

        # data[1] is the datetime when signed from itsdangerous
        if self.refresh_window and self.max_age:
            now = datetime.now(timezone.utc)
            expiration = data[1] + timedelta(seconds=self.max_age)
            # The cookie is with in the refresh window, trigger a refresh.
            if (
                now >= (expiration - timedelta(seconds=self.refresh_window))
                and now <= expiration
            ):  # noqa E501
                result.modify = True
        return result

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)

        if self.session_cookie in connection.cookies:
            scope["session"] = self.decode_cookie(
                connection.cookies[self.session_cookie].encode("utf-8")
            )  # noqa E501
        else:
            scope["session"] = ModifiedDict()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                if scope["session"] and not scope["session"].invalid:
                    # Scope has session data and is valid.
                    if scope["session"].modify:
                        # Scope has updated data or needs refreshing.
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
                # If the session cookie is invalid for any reason
                elif scope["session"].invalid:  # Clear the cookie.
                    headers = MutableHeaders(scope=message)
                    header_value = "{session_cookie}={data}; path={path}; {max_age}{security_flags}".format(  # noqa E501
                        session_cookie=self.session_cookie,
                        data="null",
                        path=self.path,
                        max_age="Max-Age=-1; ",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                # No session cookie was present, or it isn't modified,
                # don't modify or delete the cookie.
            await send(message)

        await self.app(scope, receive, send_wrapper)

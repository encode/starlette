from base64 import b64encode
from hashlib import md5
from typing import NoReturn, Optional

from starlette.datastructures import Headers, MutableHeaders
from starlette.status import HTTP_200_OK, HTTP_304_NOT_MODIFIED
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ETagMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 80) -> None:
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "GET":
            responder = ETagResponder(self.app, scope, self.minimum_size)
            await responder(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class ETagResponder:
    def __init__(self, app: ASGIApp, scope: Scope, minimum_size: int) -> None:
        self.app = app
        self.scope = scope
        self.minimum_size = minimum_size
        self.send: Send = unattached_send
        self.initial_message: Message = {}
        self.headers: Optional[MutableHeaders] = None
        self.status_code: Optional[int] = None
        self.delay_sending: bool = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.send_with_etag)

    async def send_with_etag(self, message: Message) -> None:
        if self.status_code is None:
            self.status_code = message.get("status")
        if self.status_code != HTTP_200_OK:
            if self.status_code != HTTP_304_NOT_MODIFIED:
                await self.send(message)
            # else drop the body
            return

        message_type = message["type"]
        if message_type == "http.response.start":
            self.headers = MutableHeaders(raw=message["headers"])
            etag = self.headers.get("etag")
            if etag:
                # Etag has been set, we should compare it with If-None-Match
                if self.compare_etag_with_if_none_match(etag):
                    self.status_code = message["status"] = HTTP_304_NOT_MODIFIED
                    del self.headers["content-length"]
                    await self.send(message)
                    return
                # else we don't need mofidy headers or body
            else:
                content_length = self.headers.get("content-length")
                if content_length:
                    size = int(content_length)
                    if size >= self.minimum_size:
                        # Don't send the initial message until we've determined
                        # how to modify the outgoing headers correctly.
                        self.initial_message = message
                        return
                    # else we should not send Etag
                # else it's a streamming response
            self.delay_sending = False
            await self.send(message)
        elif message_type == "http.response.body":
            if not self.delay_sending:
                await self.send(message)
                return

            # There shouldn't be more body since we have checked streamming
            # and file response before.
            assert not message.get("more_body", False)

            body = message.get("body", b"")
            if len(body) >= self.minimum_size:
                digest = md5(body).digest()
                encoded = b64encode(digest)[:-2]  # remove trailing '=='
                etag = f'''"{encoded.decode('ascii')}"'''
                assert self.headers is not None
                self.headers["etag"] = etag
                if self.compare_etag_with_if_none_match(etag):
                    del self.headers["content-length"]
                    self.initial_message["status"] = HTTP_304_NOT_MODIFIED
                    message["body"] = b""
            await self.send(self.initial_message)
            await self.send(message)

    def compare_etag_with_if_none_match(self, etag: str) -> bool:
        if_none_match = Headers(scope=self.scope).get("if-none-match")
        if if_none_match:
            if if_none_match[:2] == "W/":
                # nginx will add 'W/' prefix to ETag for gzipped content
                if_none_match = if_none_match[2:]
            return if_none_match == etag
        return False


async def unattached_send(message: Message) -> NoReturn:
    raise RuntimeError("send awaitable not set")  # pragma: no cover

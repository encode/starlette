import functools
import gzip
import io
import typing

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class GZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 500, compresslevel: int = 9) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":  # pragma: no branch
            headers = Headers(scope=scope)
            if "gzip" in headers.get("Accept-Encoding", ""):
                responder = GZipResponder(self.app, self.minimum_size, compresslevel=self.compresslevel)
                await responder(scope, receive, send)
                return
        await self.app(scope, receive, send)


class GZipResponder:
    def __init__(self, app: ASGIApp, minimum_size: int, compresslevel: int = 9) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.send: Send = unattached_send
        self.initial_message: Message = {}
        self.started = False
        self.content_encoding_set = False
        self.compresslevel = compresslevel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        with io.BytesIO() as gzip_buffer:
            with gzip.GzipFile(fileobj=gzip_buffer, mode="wb", compresslevel=self.compresslevel) as gzip_file:
                await self.app(
                    scope,
                    receive,
                    functools.partial(
                        self.send_with_gzip,
                        gzip_file=gzip_file,
                        gzip_buffer=gzip_buffer,
                    ),
                )

    async def send_with_gzip(self, message: Message, gzip_file: gzip.GzipFile, gzip_buffer: io.BytesIO) -> None:
        message_type = message["type"]
        if message_type == "http.response.start":
            # Don't send the initial message until we've determined how to
            # modify the outgoing headers correctly.
            self.initial_message = message
            headers = Headers(raw=self.initial_message["headers"])
            self.content_encoding_set = "content-encoding" in headers
        elif message_type == "http.response.body" and self.content_encoding_set:
            if not self.started:
                self.started = True
                await self.send(self.initial_message)
            await self.send(message)
        elif message_type == "http.response.body" and not self.started:
            self.started = True
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            if len(body) < self.minimum_size and not more_body:
                # Don't apply GZip to small outgoing responses.
                await self.send(self.initial_message)
                await self.send(message)
            elif not more_body:
                # Standard GZip response.
                gzip_file.write(body)
                gzip_file.close()
                body = gzip_buffer.getvalue()

                headers = MutableHeaders(raw=self.initial_message["headers"])
                headers["Content-Encoding"] = "gzip"
                headers["Content-Length"] = str(len(body))
                headers.add_vary_header("Accept-Encoding")
                message["body"] = body

                await self.send(self.initial_message)
                await self.send(message)
            else:
                # Initial body in streaming GZip response.
                headers = MutableHeaders(raw=self.initial_message["headers"])
                headers["Content-Encoding"] = "gzip"
                headers.add_vary_header("Accept-Encoding")
                del headers["Content-Length"]

                gzip_file.write(body)
                message["body"] = gzip_buffer.getvalue()
                gzip_buffer.seek(0)
                gzip_buffer.truncate()

                await self.send(self.initial_message)
                await self.send(message)

        elif message_type == "http.response.body":  # pragma: no branch
            # Remaining body in streaming GZip response.
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            gzip_file.write(body)
            if not more_body:
                gzip_file.close()

            message["body"] = gzip_buffer.getvalue()
            gzip_buffer.seek(0)
            gzip_buffer.truncate()

            await self.send(message)


async def unattached_send(message: Message) -> typing.NoReturn:
    raise RuntimeError("send awaitable not set")  # pragma: no cover

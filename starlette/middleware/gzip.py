import gzip
import io
import typing

from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    ASGISendEvent,
    HTTPResponseBodyEvent,
    HTTPResponseStartEvent,
    WWWScope,
)

from starlette.datastructures import Headers, MutableHeaders


class GZipMiddleware:
    def __init__(
        self, app: ASGI3Application, minimum_size: int = 500, compresslevel: int = 9
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def __call__(
        self, scope: WWWScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            if "gzip" in headers.get("Accept-Encoding", ""):
                responder = GZipResponder(
                    self.app, self.minimum_size, compresslevel=self.compresslevel
                )
                await responder(scope, receive, send)
                return
        await self.app(scope, receive, send)


class GZipResponder:
    def __init__(
        self, app: ASGI3Application, minimum_size: int, compresslevel: int = 9
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.send: ASGISendCallable = unattached_send
        self.initial_message: ASGISendEvent = HTTPResponseStartEvent(
            type="http.response.start", status=200, headers=()
        )
        self.started = False
        self.gzip_buffer = io.BytesIO()
        self.gzip_file = gzip.GzipFile(
            mode="wb", fileobj=self.gzip_buffer, compresslevel=compresslevel
        )

    async def __call__(
        self, scope: WWWScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        self.send = send
        await self.app(scope, receive, self.send_with_gzip)

    async def send_with_gzip(self, message: ASGISendEvent) -> None:
        message_type = message["type"]
        if message_type == "http.response.start":
            # Don't send the initial message until we've determined how to
            # modify the outgoing headers correctly.
            message_status = message.get("status")
            message_headers = message.get("headers")
            assert isinstance(message_status, int)
            assert isinstance(message_headers, typing.Iterable)
            self.initial_message = HTTPResponseStartEvent(
                type=message_type, status=message_status, headers=message_headers
            )
        elif message_type == "http.response.body" and not self.started:
            self.started = True
            body = message.get("body", b"")
            assert isinstance(body, bytes)
            more_body = bool(message.get("more_body", False))
            message = HTTPResponseBodyEvent(
                type=message_type, body=body, more_body=more_body
            )
            if len(body) < self.minimum_size and not more_body:
                # Don't apply GZip to small outgoing responses.
                await self.send(self.initial_message)
                await self.send(message)
            elif not more_body:
                # Standard GZip response.
                self.gzip_file.write(body)
                self.gzip_file.close()
                body = self.gzip_buffer.getvalue()
                raw_headers = self.initial_message.get("headers")
                headers = MutableHeaders(raw=raw_headers)  # type: ignore[arg-type]
                headers["Content-Encoding"] = "gzip"
                headers["Content-Length"] = str(len(body))
                headers.add_vary_header("Accept-Encoding")
                message["body"] = body

                await self.send(self.initial_message)
                await self.send(message)
            else:
                # Initial body in streaming GZip response.
                raw_headers = self.initial_message.get("headers")
                headers = MutableHeaders(raw=raw_headers)  # type: ignore[arg-type]
                headers["Content-Encoding"] = "gzip"
                headers.add_vary_header("Accept-Encoding")
                del headers["Content-Length"]

                self.gzip_file.write(body)
                message["body"] = self.gzip_buffer.getvalue()
                self.gzip_buffer.seek(0)
                self.gzip_buffer.truncate()

                await self.send(self.initial_message)
                await self.send(message)

        elif message_type == "http.response.body":
            # Remaining body in streaming GZip response.
            body = message.get("body", b"")
            assert isinstance(body, bytes)
            more_body = bool(message.get("more_body", False))
            message = HTTPResponseBodyEvent(
                type=message_type, body=body, more_body=more_body
            )

            self.gzip_file.write(body)
            if not more_body:
                self.gzip_file.close()

            message["body"] = self.gzip_buffer.getvalue()
            self.gzip_buffer.seek(0)
            self.gzip_buffer.truncate()

            await self.send(message)


async def unattached_send(message: ASGISendEvent) -> typing.NoReturn:
    raise RuntimeError("send awaitable not set")  # pragma: no cover

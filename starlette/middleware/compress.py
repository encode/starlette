from __future__ import annotations

import gzip
import platform
import re
from functools import lru_cache
from io import BytesIO
from typing import TYPE_CHECKING, NoReturn

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_missing_packages: list[str] = []

if platform.python_implementation() == "CPython":
    try:
        try:
            import brotli
        except ModuleNotFoundError:  # pragma: nocover
            import brotlicffi as brotli
    except ModuleNotFoundError:  # pragma: nocover
        _missing_packages.append("brotli")
else:  # pragma: nocover
    try:
        try:
            import brotlicffi as brotli
        except ModuleNotFoundError:
            import brotli
    except ModuleNotFoundError:
        _missing_packages.append("brotlicffi")

try:
    from zstandard import ZstdCompressor

    if TYPE_CHECKING:  # pragma: nocover
        from zstandard import ZstdCompressionChunker
except ModuleNotFoundError:  # pragma: nocover
    _missing_packages.append("zstandard")

if _missing_packages:  # pragma: nocover
    missing_packages_and = " and ".join(_missing_packages)
    missing_packages_space = " ".join(_missing_packages)
    raise RuntimeError(
        "The starlette.middleware.compress module requires "
        f"the {missing_packages_and} package to be installed.\n"
        "You can install this with:\n"
        f"    $ pip install {missing_packages_space}\n"
    )


class CompressMiddleware:
    """
    Response compressing middleware.
    """

    __slots__ = (
        "app",
        "minimum_size",
        "gzip",
        "gzip_level",
        "brotli",
        "brotli_quality",
        "zstd",
        "zstd_compressor",
    )

    def __init__(
        self,
        app: ASGIApp,
        *,
        minimum_size: int = 500,
        gzip: bool = True,
        gzip_level: int = 4,
        brotli: bool = True,
        brotli_quality: int = 4,
        zstd: bool = True,
        zstd_level: int = 4,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.gzip = gzip
        self.gzip_level = gzip_level
        self.brotli = brotli
        self.brotli_quality = brotli_quality
        self.zstd = zstd
        self.zstd_compressor = ZstdCompressor(level=zstd_level)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            accept_encoding = Headers(scope=scope).get("Accept-Encoding")

            if not accept_encoding:
                await self.app(scope, receive, send)
                return

            accept_encodings = parse_accept_encoding(accept_encoding)

            if self.zstd and "zstd" in accept_encodings:
                await _ZstdResponder(self.app, self.minimum_size, self.zstd_compressor)(
                    scope, receive, send
                )
                return
            elif self.brotli and "br" in accept_encodings:
                await _BrotliResponder(
                    self.app, self.minimum_size, self.brotli_quality
                )(scope, receive, send)
                return
            elif self.gzip and "gzip" in accept_encodings:
                await _GZipResponder(self.app, self.minimum_size, self.gzip_level)(
                    scope, receive, send
                )
                return

        await self.app(scope, receive, send)


class _ZstdResponder:
    __slots__ = (
        "app",
        "minimum_size",
        "compressor",
        "chunker",
        "send",
        "start_message",
    )

    def __init__(
        self, app: ASGIApp, minimum_size: int, compressor: ZstdCompressor
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compressor = compressor
        self.chunker: ZstdCompressionChunker | None = None
        self.send: Send = _unattached_send
        self.start_message: Message | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.wrapper)

    async def wrapper(self, message: Message) -> None:
        message_type: str = message["type"]

        # handle start message
        if message_type == "http.response.start":
            if self.start_message is not None:  # pragma: nocover
                raise AssertionError("Unexpected repeated http.response.start message")

            if _is_start_message_satisfied(message):
                # capture start message and wait for response body
                self.start_message = message
                return
            else:
                await self.send(message)
                return

        # skip if start message is not satisfied or unknown message type
        if self.start_message is None or message_type != "http.response.body":
            await self.send(message)
            return

        body: bytes = message.get("body", b"")
        more_body: bool = message.get("more_body", False)

        if self.chunker is None:
            # skip compression for small responses
            if not more_body and len(body) < self.minimum_size:
                await self.send(self.start_message)
                await self.send(message)
                return

            headers = MutableHeaders(raw=self.start_message["headers"])
            headers["Content-Encoding"] = "zstd"
            headers.add_vary_header("Accept-Encoding")

            if not more_body:
                # one-shot
                compressed_body = self.compressor.compress(body)
                headers["Content-Length"] = str(len(compressed_body))
                message["body"] = compressed_body
                await self.send(self.start_message)
                await self.send(message)
                return

            # begin streaming
            content_length: int = int(headers.get("Content-Length", -1))
            del headers["Content-Length"]
            await self.send(self.start_message)
            self.chunker = self.compressor.chunker(content_length)

        # streaming
        for chunk in self.chunker.compress(body):
            await self.send(
                {"type": "http.response.body", "body": chunk, "more_body": True}
            )
        if more_body:
            return
        for chunk in self.chunker.finish():  # type: ignore
            await self.send(
                {"type": "http.response.body", "body": chunk, "more_body": True}
            )

        await self.send({"type": "http.response.body"})


class _BrotliResponder:
    __slots__ = (
        "app",
        "minimum_size",
        "quality",
        "compressor",
        "send",
        "start_message",
    )

    def __init__(self, app: ASGIApp, minimum_size: int, quality: int) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.quality = quality
        self.compressor: brotli.Compressor | None = None
        self.send: Send = _unattached_send
        self.start_message: Message | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.wrapper)

    async def wrapper(self, message: Message) -> None:
        message_type: str = message["type"]

        # handle start message
        if message_type == "http.response.start":
            if self.start_message is not None:  # pragma: nocover
                raise AssertionError("Unexpected repeated http.response.start message")

            if _is_start_message_satisfied(message):
                # capture start message and wait for response body
                self.start_message = message
                return
            else:
                await self.send(message)
                return

        # skip if start message is not satisfied or unknown message type
        if self.start_message is None or message_type != "http.response.body":
            await self.send(message)
            return

        body: bytes = message.get("body", b"")
        more_body: bool = message.get("more_body", False)

        if self.compressor is None:
            # skip compression for small responses
            if not more_body and len(body) < self.minimum_size:
                await self.send(self.start_message)
                await self.send(message)
                return

            headers = MutableHeaders(raw=self.start_message["headers"])
            headers["Content-Encoding"] = "br"
            headers.add_vary_header("Accept-Encoding")

            if not more_body:
                # one-shot
                compressed_body = brotli.compress(body, quality=self.quality)
                headers["Content-Length"] = str(len(compressed_body))
                message["body"] = compressed_body
                await self.send(self.start_message)
                await self.send(message)
                return

            # begin streaming
            del headers["Content-Length"]
            await self.send(self.start_message)
            self.compressor = brotli.Compressor(quality=self.quality)

        # streaming
        chunk = self.compressor.process(body)
        if chunk:
            await self.send(
                {"type": "http.response.body", "body": chunk, "more_body": True}
            )
        if more_body:
            return
        chunk = self.compressor.finish()
        await self.send({"type": "http.response.body", "body": chunk})


class _GZipResponder:
    __slots__ = (
        "app",
        "minimum_size",
        "level",
        "compressor",
        "buffer",
        "send",
        "start_message",
    )

    def __init__(self, app: ASGIApp, minimum_size: int, level: int) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.level = level
        self.compressor: gzip.GzipFile | None = None
        self.buffer: BytesIO | None = None
        self.send: Send = _unattached_send
        self.start_message: Message | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.wrapper)

    async def wrapper(self, message: Message) -> None:
        message_type: str = message["type"]

        # handle start message
        if message_type == "http.response.start":
            if self.start_message is not None:  # pragma: nocover
                raise AssertionError("Unexpected repeated http.response.start message")

            if _is_start_message_satisfied(message):
                # capture start message and wait for response body
                self.start_message = message
                return
            else:
                await self.send(message)
                return

        # skip if start message is not satisfied or unknown message type
        if self.start_message is None or message_type != "http.response.body":
            await self.send(message)
            return

        body: bytes = message.get("body", b"")
        more_body: bool = message.get("more_body", False)

        if self.compressor is None:
            # skip compression for small responses
            if not more_body and len(body) < self.minimum_size:
                await self.send(self.start_message)
                await self.send(message)
                return

            headers = MutableHeaders(raw=self.start_message["headers"])
            headers["Content-Encoding"] = "gzip"
            headers.add_vary_header("Accept-Encoding")

            if not more_body:
                # one-shot
                compressed_body = gzip.compress(body, compresslevel=self.level)
                headers["Content-Length"] = str(len(compressed_body))
                message["body"] = compressed_body
                await self.send(self.start_message)
                await self.send(message)
                return

            # begin streaming
            del headers["Content-Length"]
            await self.send(self.start_message)
            self.buffer = BytesIO()
            self.compressor = gzip.GzipFile(
                mode="wb", compresslevel=self.level, fileobj=self.buffer
            )

        if self.buffer is None:  # pragma: nocover
            raise AssertionError("Compressor is set but buffer is not")

        # streaming
        self.compressor.write(body)
        if not more_body:
            self.compressor.close()
        compressed_body = self.buffer.getvalue()
        if more_body:
            if compressed_body:
                self.buffer.seek(0)
                self.buffer.truncate()
            else:
                return
        await self.send(
            {
                "type": "http.response.body",
                "body": compressed_body,
                "more_body": more_body,
            }
        )


_accept_encoding_re = re.compile(r"[a-z]{2,8}")


@lru_cache(maxsize=128)
def parse_accept_encoding(accept_encoding: str) -> frozenset[str]:
    """
    Parse the accept encoding header and return a set of supported encodings.

    >>> parse_accept_encoding('br;q=1.0, gzip;q=0.8, *;q=0.1')
    {'br', 'gzip'}
    """
    return frozenset(_accept_encoding_re.findall(accept_encoding))


# Primarily based on:
# https://github.com/h5bp/server-configs-nginx/blob/main/h5bp/web_performance/compression.conf#L38
_compress_content_types: set[str] = {
    "application/atom+xml",
    "application/geo+json",
    "application/javascript",
    "application/x-javascript",
    "application/json",
    "application/ld+json",
    "application/manifest+json",
    "application/rdf+xml",
    "application/rss+xml",
    "application/vnd.mapbox-vector-tile",
    "application/vnd.ms-fontobject",
    "application/wasm",
    "application/x-web-app-manifest+json",
    "application/xhtml+xml",
    "application/xml",
    "font/eot",
    "font/otf",
    "font/ttf",
    "image/bmp",
    "image/svg+xml",
    "image/vnd.microsoft.icon",
    "image/x-icon",
    "text/cache-manifest",
    "text/calendar",
    "text/css",
    "text/html",
    "text/javascript",
    "text/markdown",
    "text/plain",
    "text/xml",
    "text/vcard",
    "text/vnd.rim.location.xloc",
    "text/vtt",
    "text/x-component",
    "text/x-cross-domain-policy",
}


def register_compress_content_type(content_type: str) -> None:
    """
    Register a new content type to be compressed.
    """
    _compress_content_types.add(content_type)


def deregister_compress_content_type(content_type: str) -> None:
    """
    Deregister a content type from being compressed.
    """
    _compress_content_types.discard(content_type)


def _is_start_message_satisfied(message: Message) -> bool:
    """
    Check if response should be compressed based on the start message.
    """
    headers = Headers(raw=message["headers"])

    # must not already be compressed
    if "Content-Encoding" in headers:
        return False

    # content type header must be present
    content_type = headers.get("Content-Type")
    if not content_type:
        return False

    # must be a compressible content type
    basic_content_type = content_type.partition(";")[0].strip()
    return basic_content_type in _compress_content_types


async def _unattached_send(message: Message) -> NoReturn:  # pragma: nocover
    raise RuntimeError("send awaitable not set")

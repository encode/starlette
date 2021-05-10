import os
import stat
import typing
from email.utils import parsedate

from aiofiles.os import stat as aio_stat
from importlib_resources.readers import MultiplexedPath

from starlette.datastructures import Headers
from starlette.responses import (
    FileResponse,
    PlainTextResponse,
    Response,
)
from starlette.types import Receive, Scope, Send

PathLike = typing.Union[str, "os.PathLike[str]"]


class NotModifiedResponse(Response):
    NOT_MODIFIED_HEADERS = (
        "cache-control",
        "content-location",
        "date",
        "etag",
        "expires",
        "vary",
    )

    def __init__(self, headers: Headers):
        super().__init__(
            status_code=304,
            headers={
                name: value
                for name, value in headers.items()
                if name in self.NOT_MODIFIED_HEADERS
            },
        )


class StaticResources:
    def __init__(
        self,
        resources: MultiplexedPath,
        *,
        html: bool = False,
    ) -> None:
        self.resources = resources
        self.html = html

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        The ASGI entry point.
        """
        assert scope["type"] == "http"

        path = self.get_path(scope)
        response = await self.get_response(path, scope)
        await response(scope, receive, send)

    def get_path(self, scope: Scope) -> str:
        """
        Given the ASGI scope, return the `path` string to serve up,
        with OS specific path seperators, and any '..', '.' components removed.
        """
        return os.path.normpath(os.path.join(*scope["path"].split("/")))

    async def get_response(self, path: str, scope: Scope) -> Response:
        """
        Returns an HTTP response, given the incoming path, method and request headers.
        """
        if scope["method"] not in ("GET", "HEAD"):
            return PlainTextResponse("Method Not Allowed", status_code=405)

        full_path, stat_result = await self.lookup_path(path)

        if stat_result and stat.S_ISREG(stat_result.st_mode):
            # We have a static file to serve.
            return self.file_response(full_path, stat_result, scope)

        return PlainTextResponse("Not Found", status_code=404)

    async def lookup_path(
        self, path: str
    ) -> typing.Tuple[str, typing.Optional[os.stat_result]]:
        p = self.resources.joinpath(path)
        if not p.is_file():
            return "", None

        stat_result = await aio_stat(p)
        return p, stat_result

    def file_response(
        self,
        full_path: PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        method = scope["method"]
        request_headers = Headers(scope=scope)

        response = FileResponse(
            full_path, status_code=status_code, stat_result=stat_result, method=method
        )
        if self.is_not_modified(response.headers, request_headers):
            return NotModifiedResponse(response.headers)
        return response

    def is_not_modified(
        self, response_headers: Headers, request_headers: Headers
    ) -> bool:
        """
        Given the request and response headers, return `True` if an HTTP
        "Not Modified" response could be returned instead.
        """
        try:
            if_none_match = request_headers["if-none-match"]
            etag = response_headers["etag"]
            if if_none_match == etag:
                return True
        except KeyError:
            pass

        try:
            if_modified_since = parsedate(request_headers["if-modified-since"])
            last_modified = parsedate(response_headers["last-modified"])
            if (
                if_modified_since is not None
                and last_modified is not None
                and if_modified_since >= last_modified
            ):
                return True
        except KeyError:
            pass

        return False

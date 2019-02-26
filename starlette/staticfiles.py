import functools
import importlib
import os
import stat
import typing
from email.utils import parsedate

from aiofiles.os import stat as aio_stat

from starlette.datastructures import Headers
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.types import ASGIInstance, Receive, Scope, Send


class NotModifiedResponse(Response):
    NOT_MODIFIED_HEADERS = (
        "cache-control",
        "content-location",
        "date",
        "etag",
        "expires",
        "vary",
    )

    def __init__(self, stat_headers: dict):
        headers = {
            name: value
            for name, value in stat_headers.items()
            if name in self.NOT_MODIFIED_HEADERS
        }
        return super().__init__(status_code=304, headers=headers)


class StaticFiles:
    def __init__(self, *, directory: str, packages: typing.List[str] = None, check_dir: bool = True) -> None:
        self.directory = directory
        self.packages = packages
        self.config_checked = False
        if check_dir and not os.path.isdir(directory):
            raise RuntimeError(f"Directory '{directory}' does not exist")

    def _get_package_dirs(self, packages: typing.List[str] = None) -> typing.List[str]:
        directories = []
        for package in packages or []:
            spec = importlib.util.find_spec(package)
            assert spec is not None, f"Package {package!r} could not be found."
            directory = os.path.join(spec.origin, "..", "statics")
            assert os.path.isdir(directory), "Directory 'statics' in package {package!r} could not be found."
            directories.append(directory)
        return directories

    def __call__(self, scope: Scope) -> ASGIInstance:
        assert scope["type"] == "http"

        if scope["method"] not in ("GET", "HEAD"):
            return PlainTextResponse("Method Not Allowed", status_code=405)

        path = os.path.normpath(os.path.join(*scope["path"].split("/")))
        if path.startswith(".."):
            return PlainTextResponse("Not Found", status_code=404)

        path = os.path.join(self.directory, path)
        return functools.partial(self.asgi, scope=scope)

    async def asgi(self, receive: Receive, send: Send, scope: Scope) -> None:
        if not self.config_checked:
            await self.check_config()
            self.config_checked = True

        path = os.path.normpath(os.path.join(*scope["path"].split("/")))
        method = scope["method"]
        headers = Headers(scope=scope)
        response = await self.get_response(path, method, headers)
        await response(receive, send)

    async def get_response(self, path: str, method: str, headers: Headers) -> Response:
        if path.startswith(".."):
            return PlainTextResponse("Not Found", status_code=404)

        path = os.path.join(self.directory, path)
        try:
            stat_result = await aio_stat(path)
        except FileNotFoundError:
            return PlainTextResponse("Not Found", status_code=404)

        mode = stat_result.st_mode
        if not stat.S_ISREG(mode):
            return PlainTextResponse("Not Found", status_code=404)

        stat_headers = FileResponse.get_stat_headers(stat_result)
        if self.is_not_modified(stat_headers, headers):
            return NotModifiedResponse(stat_headers)

        return FileResponse(path, stat_result=stat_result, method=method)

    async def check_config(self) -> None:
        """
        Perform a one-off configuration check that StaticFiles is actually
        pointed at a directory, so that we can raise loud errors rather than
        just returning 404 responses.
        """
        try:
            stat_result = await aio_stat(self.directory)
        except FileNotFoundError:
            raise RuntimeError(f"StaticFiles directory '{self.directory}' does not exist.")
        if not (stat.S_ISDIR(stat_result.st_mode) or stat.S_ISLNK(stat_result.st_mode)):
            raise RuntimeError(f"StaticFiles path '{self.directory}' is not a directory.")

    def is_not_modified(self, stat_headers: typing.Dict[str, str], request_headers: Headers) -> bool:
        etag = stat_headers["etag"]
        last_modified = stat_headers["last-modified"]
        if etag == request_headers.get("if-none-match"):
            return True
        if "if-modified-since" not in request_headers:
            return False
        if_modified_since = request_headers["if-modified-since"]
        return parsedate(if_modified_since) >= parsedate(last_modified)  # type: ignore

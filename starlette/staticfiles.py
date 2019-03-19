import importlib.util
import os
import stat
import typing
from email.utils import parsedate

from aiofiles.os import stat as aio_stat

from starlette.datastructures import Headers
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.types import Receive, Scope, Send


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
        return super().__init__(
            status_code=304,
            headers={
                name: value
                for name, value in headers.items()
                if name in self.NOT_MODIFIED_HEADERS
            },
        )


class StaticFiles:
    def __init__(
        self,
        *,
        directory: str = None,
        packages: typing.List[str] = None,
        html: bool = False,
        check_dir: bool = True,
    ) -> None:
        self.directory = directory
        self.packages = packages
        self.all_directories = self.get_directories(directory, packages)
        self.html = html
        self.config_checked = False
        if check_dir and directory is not None and not os.path.isdir(directory):
            raise RuntimeError(f"Directory '{directory}' does not exist")

    def get_directories(
        self, directory: str = None, packages: typing.List[str] = None
    ) -> typing.List[str]:
        """
        Given `directory` and `packages` arugments, return a list of all the
        directories that should be used for serving static files from.
        """
        directories = []
        if directory is not None:
            directories.append(directory)

        for package in packages or []:
            spec = importlib.util.find_spec(package)
            assert spec is not None, f"Package {package!r} could not be found."
            assert (
                spec.origin is not None
            ), "Directory 'statics' in package {package!r} could not be found."
            directory = os.path.normpath(os.path.join(spec.origin, "..", "statics"))
            assert os.path.isdir(
                directory
            ), "Directory 'statics' in package {package!r} could not be found."
            directories.append(directory)

        return directories

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        The ASGI entry point.
        """
        assert scope["type"] == "http"

        if not self.config_checked:
            await self.check_config()
            self.config_checked = True

        path = self.get_path(scope)
        method = scope["method"]
        headers = Headers(scope=scope)
        response = await self.get_response(path, method, headers)
        await response(scope, receive, send)

    def get_path(self, scope: Scope) -> str:
        """
        Given the ASGI scope, return the `path` string to serve up,
        with OS specific path seperators, and any '..', '.' components removed.
        """
        return os.path.normpath(os.path.join(*scope["path"].split("/")))

    async def get_response(
        self, path: str, method: str, request_headers: Headers
    ) -> Response:
        """
        Returns an HTTP response, given the incoming path, method and request headers.
        """
        if method not in ("GET", "HEAD"):
            return PlainTextResponse("Method Not Allowed", status_code=405)

        if path.startswith(".."):
            return PlainTextResponse("Not Found", status_code=404)

        full_path, stat_result = await self.lookup_path(path)

        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            if self.html:
                # Check for 'index.html' if we're in HTML mode.
                if stat_result is not None and stat.S_ISDIR(stat_result.st_mode):
                    index_path = os.path.join(path, "index.html")
                    full_path, stat_result = await self.lookup_path(index_path)
                    if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
                        return self.file_response(
                            full_path, stat_result, method, request_headers
                        )

                # Check for '404.html' if we're in HTML mode.
                full_path, stat_result = await self.lookup_path("404.html")
                if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
                    return FileResponse(
                        full_path,
                        stat_result=stat_result,
                        method=method,
                        status_code=404,
                    )

            return PlainTextResponse("Not Found", status_code=404)

        return self.file_response(full_path, stat_result, method, request_headers)

    async def lookup_path(
        self, path: str
    ) -> typing.Tuple[str, typing.Optional[os.stat_result]]:
        stat_result = None
        for directory in self.all_directories:
            full_path = os.path.join(directory, path)
            try:
                stat_result = await aio_stat(full_path)
                return (full_path, stat_result)
            except FileNotFoundError:
                pass
        return ("", None)

    def file_response(
        self,
        full_path: str,
        stat_result: os.stat_result,
        method: str,
        request_headers: Headers,
    ) -> Response:
        response = FileResponse(full_path, stat_result=stat_result, method=method)
        if self.is_not_modified(response.headers, request_headers):
            return NotModifiedResponse(response.headers)
        return response

    async def check_config(self) -> None:
        """
        Perform a one-off configuration check that StaticFiles is actually
        pointed at a directory, so that we can raise loud errors rather than
        just returning 404 responses.
        """
        if self.directory is None:
            return

        try:
            stat_result = await aio_stat(self.directory)
        except FileNotFoundError:
            raise RuntimeError(
                f"StaticFiles directory '{self.directory}' does not exist."
            )
        if not (stat.S_ISDIR(stat_result.st_mode) or stat.S_ISLNK(stat_result.st_mode)):
            raise RuntimeError(
                f"StaticFiles path '{self.directory}' is not a directory."
            )

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

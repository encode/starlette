from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, ASGIInstance, Scope
import typing

def _is_trusted_host(
    host: str, allowed_hosts: typing.Sequence[str]
) -> bool:
    """
    Check if the host matchs the pattern.

    Any given pattern starting with a period is considered a wildcard pattern.
    """
    host = host.lower()
    for pattern in allowed_hosts:
        if (
            pattern == "*" or pattern == host or
            pattern[0] == "." and
            (host.endswith(pattern) or host == pattern[1:])
        ):
            return True
    return False

class TrustedHostMiddleware:
    def __init__(
        self, app: ASGIApp, allowed_hosts: typing.Sequence[str] = ["*"]
    ) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts
        self.allow_any = "*" in allowed_hosts

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] in ("http", "websocket") and not self.allow_any:
            headers = Headers(scope=scope)
            host = headers.get("host").split(":")[0]
            if not _is_trusted_host(host, self.allowed_hosts):
                return PlainTextResponse("Invalid host header", status_code=400)

        return self.app(scope)

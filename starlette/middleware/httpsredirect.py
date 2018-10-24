from starlette.datastructures import URL
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, ASGIInstance, Scope
from starlette import status


class HTTPSRedirectMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] in ("http", "websocket") and scope["scheme"] in ("http", "ws"):
            redirect_scheme = {"http": "https", "ws": "wss"}[scope["scheme"]]
            url = URL(scope=scope)
            url = url.replace(scheme=redirect_scheme, netloc=url.hostname)
            return RedirectResponse(url, status_code=status.HTTP_301_MOVED_PERMANENTLY)

        return self.app(scope)

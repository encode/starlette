import functools
import urllib

import sentry_sdk
from sentry_sdk.utils import event_from_exception, exc_info_from_error

from starlette.requests import Request


class SentryMiddleware:
    def __init__(self, app, sentry_dsn):
        self.app = app
        sentry_sdk.init(sentry_dsn)

    def __call__(self, scope):
        return functools.partial(self.asgi, asgi_scope=scope)

    async def asgi(self, receive, send, asgi_scope):
        hub = sentry_sdk.Hub.current
        with sentry_sdk.Hub(hub) as hub:
            with hub.configure_scope() as sentry_scope:
                try:
                    inner = self.app(asgi_scope)
                    await inner(receive, send)
                except Exception as exc:
                    request = Request(scope=asgi_scope)
                    exc_info = exc_info_from_error(exc)
                    event, hint = event_from_exception(
                        exc_info, client_options=hub.client.options
                    )
                    event["request"] = {
                        "url": str(request.url.replace(query="")),
                        "method": request.method,
                        "headers": dict(request.headers),
                        "query_string": request.url.query,
                    }
                    if asgi_scope.get("client"):
                        event["request"]["env"] = {
                            "REMOTE_ADDR": asgi_scope["client"][0]
                        }
                    if asgi_scope.get("endpoint"):
                        event["transaction"] = self.get_transaction(
                            asgi_scope["endpoint"]
                        )
                    hub.capture_event(event, hint=hint)
                    raise exc from None

    def get_transaction(self, endpoint):
        qualname = (
            getattr(endpoint, "__qualname__", None)
            or getattr(endpoint, "__name__", None)
            or None
        )
        if not qualname:
            return None
        return "%s.%s" % (endpoint.__module__, qualname)

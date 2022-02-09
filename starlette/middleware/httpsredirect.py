from typing import Mapping

from starlette.datastructures import URL
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebsocketDenialResponse


class HTTPSRedirectMiddleware:
    def __init__(
        self, app: ASGIApp, port_mapping: Mapping[int, int] = {80: 443}
    ) -> None:
        self.app = app
        self.port_mapping = port_mapping

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and scope["scheme"] in ("http", "ws"):
            url = URL(scope=scope)
            new_scheme = {"http": "https", "ws": "wss"}[url.scheme]

            # Map the port
            old_port = url.port or 80  # HTTP/WS default to port 80
            new_port = self.port_mapping.get(old_port, old_port)
            if new_port == 443:  # Suppress HTTPS/WSS port 443
                new_port = None
            url = url.replace(scheme=new_scheme, port=new_port)
            response = RedirectResponse(url, status_code=307)
            if scope["type"] == "websocket":
                response = WebsocketDenialResponse(response)
            await response(scope, receive, send)
        else:
            await self.app(scope, receive, send)

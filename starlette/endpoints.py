from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.websockets import WebSocket
from starlette.responses import Response, PlainTextResponse
from starlette.types import Receive, Send, Scope
import asyncio


class HTTPEndpoint:
    def __init__(self, scope: Scope):
        self.scope = scope

    async def __call__(self, receive: Receive, send: Send):
        request = Request(self.scope, receive=receive)
        kwargs = self.scope.get("kwargs", {})
        response = await self.dispatch(request, **kwargs)
        await response(receive, send)

    async def dispatch(self, request: Request, **kwargs) -> Response:
        handler_name = "get" if request.method == "HEAD" else request.method.lower()
        handler = getattr(self, handler_name, self.method_not_allowed)
        if asyncio.iscoroutinefunction(handler):
            response = await handler(request, **kwargs)
        else:
            response = handler(request, **kwargs)
        return response

    async def method_not_allowed(self, request: Request, **kwargs) -> Response:
        # If we're running inside a starlette application then raise an
        # exception, so that the configurable exception handler can deal with
        # returning the response. For plain ASGI apps, just return the response.
        if "app" in self.scope:
            raise HTTPException(status_code=405)
        return PlainTextResponse("Method Not Allowed", status_code=405)


class WebSocketEndpoint:
    def __init__(self, scope: Scope):
        self.scope = scope
        self.websocket = None
        self.close_code = None
        self.kwargs = None

    async def __call__(self, receive: Receive, send: Send):
        self.websocket = WebSocket(self.scope, receive=receive, send=send)
        self.kwargs = self.scope.get("kwargs", {})
        await self.on_connect()

        try:
            while True:
                message = await self.websocket.receive()
                if message["type"] == "websocket.receive":
                    if "text" in message:
                        await self.on_receive(text=message["text"])
                    else:
                        await self.on_receive(bytes=message["bytes"])
                elif message["type"] == "websocket.disconnect":
                    self.close_code = message.get("code", 1000)
                    return
        finally:
            await self.on_disconnect()

    async def on_connect(self):
        """Override to handle an incoming websocket connection"""
        await self.websocket.accept()

    async def on_receive(self, bytes=None, text=None):
        """Override to handle an incoming websocket message"""

    async def on_disconnect(self):
        """Override to handle a disconnecting websocket"""

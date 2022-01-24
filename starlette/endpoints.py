import asyncio
import json
import typing

from asgiref.typing import (
    ASGIReceiveCallable,
    ASGISendCallable,
    HTTPScope,
    WebSocketReceiveEvent,
    WebSocketScope,
)

from starlette import status
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.websockets import WebSocket


class HTTPEndpoint:
    def __init__(
        self, scope: HTTPScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        assert scope["type"] == "http"
        self.scope = scope
        self.receive = receive
        self.send = send

    def __await__(self) -> typing.Generator:
        return self.dispatch().__await__()

    async def dispatch(self) -> None:
        request = Request(self.scope, receive=self.receive)
        handler_name = (
            "get"
            if request.method == "HEAD" and not hasattr(self, "head")
            else request.method.lower()
        )

        handler: typing.Callable[[Request], typing.Any] = getattr(
            self, handler_name, self.method_not_allowed
        )
        is_async = asyncio.iscoroutinefunction(handler)
        if is_async:
            response = await handler(request)
        else:
            response = await run_in_threadpool(handler, request)
        await response(self.scope, self.receive, self.send)

    async def method_not_allowed(self, request: Request) -> Response:
        # If we're running inside a starlette application then raise an
        # exception, so that the configurable exception handler can deal with
        # returning the response. For plain ASGI apps, just return the response.
        if "app" in self.scope:
            raise HTTPException(status_code=405)
        return PlainTextResponse("Method Not Allowed", status_code=405)


class WebSocketEndpoint:

    encoding: typing.Optional[str] = None  # May be "text", "bytes", or "json".

    def __init__(
        self,
        scope: WebSocketScope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        assert scope["type"] == "websocket"
        self.scope = scope
        self.receive = receive
        self.send = send

    def __await__(self) -> typing.Generator:
        return self.dispatch().__await__()

    async def dispatch(self) -> None:
        websocket = WebSocket(self.scope, receive=self.receive, send=self.send)
        await self.on_connect(websocket)

        close_code = status.WS_1000_NORMAL_CLOSURE

        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.receive":
                    data = await self.decode(websocket, message)
                    await self.on_receive(websocket, data)
                elif message["type"] == "websocket.disconnect":
                    close_code = int(message.get("code", status.WS_1000_NORMAL_CLOSURE))
                    break
        except Exception as exc:
            close_code = status.WS_1011_INTERNAL_ERROR
            raise exc
        finally:
            await self.on_disconnect(websocket, close_code)

    async def decode(
        self, websocket: WebSocket, message: WebSocketReceiveEvent
    ) -> typing.Any:

        if self.encoding == "text":
            if message.get("text") is None:
                await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                raise RuntimeError("Expected text websocket messages, but got bytes")
            return message["text"]

        elif self.encoding == "bytes":
            if message.get("bytes") is None:
                await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                raise RuntimeError("Expected bytes websocket messages, but got text")
            return message["bytes"]

        elif self.encoding == "json":
            if message.get("text") is not None:
                text = message["text"]
                assert isinstance(text, str)
            else:
                message_bytes = message.get("bytes")
                assert isinstance(message_bytes, bytes)
                text = message_bytes.decode("utf-8")

            try:
                return json.loads(text)
            except json.decoder.JSONDecodeError:
                await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                raise RuntimeError("Malformed JSON data received.")

        assert (
            self.encoding is None
        ), f"Unsupported 'encoding' attribute {self.encoding}"
        return message["text"] if message.get("text") else message["bytes"]

    async def on_connect(self, websocket: WebSocket) -> None:
        """Override to handle an incoming websocket connection"""
        await websocket.accept()

    async def on_receive(self, websocket: WebSocket, data: typing.Any) -> None:
        """Override to handle an incoming websocket message"""

    async def on_disconnect(self, websocket: WebSocket, close_code: int) -> None:
        """Override to handle a disconnecting websocket"""

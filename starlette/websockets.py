import enum
import json
import typing

from asgiref.typing import (
    ASGIReceiveCallable,
    ASGIReceiveEvent,
    ASGISendCallable,
    ASGISendEvent,
    WebSocketAcceptEvent,
    WebSocketCloseEvent,
    WebSocketSendEvent,
    WWWScope,
)

from starlette.requests import HTTPConnection


class WebSocketState(enum.Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000) -> None:
        self.code = code


class WebSocket(HTTPConnection):
    def __init__(
        self, scope: WWWScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        super().__init__(scope)
        assert scope["type"] == "websocket"
        self._receive = receive
        self._send = send
        self.client_state = WebSocketState.CONNECTING
        self.application_state = WebSocketState.CONNECTING

    async def receive(self) -> ASGIReceiveEvent:
        """
        Receive ASGI websocket messages, ensuring valid state transitions.
        """
        if self.client_state == WebSocketState.CONNECTING:
            message = await self._receive()
            message_type = message["type"]
            assert message_type == "websocket.connect"
            self.client_state = WebSocketState.CONNECTED
            return message
        elif self.client_state == WebSocketState.CONNECTED:
            message = await self._receive()
            message_type = message["type"]
            assert message_type in {"websocket.receive", "websocket.disconnect"}
            if message_type == "websocket.disconnect":
                self.client_state = WebSocketState.DISCONNECTED
            return message
        else:
            raise RuntimeError(
                'Cannot call "receive" once a disconnect message has been received.'
            )

    async def send(self, message: ASGISendEvent) -> None:
        """
        Send ASGI websocket messages, ensuring valid state transitions.
        """
        if self.application_state == WebSocketState.CONNECTING:
            message_type = message["type"]
            assert message_type in {"websocket.accept", "websocket.close"}
            if message_type == "websocket.close":
                self.application_state = WebSocketState.DISCONNECTED
            else:
                self.application_state = WebSocketState.CONNECTED
            await self._send(message)
        elif self.application_state == WebSocketState.CONNECTED:
            message_type = message["type"]
            assert message_type in {"websocket.send", "websocket.close"}
            if message_type == "websocket.close":
                self.application_state = WebSocketState.DISCONNECTED
            await self._send(message)
        else:
            raise RuntimeError('Cannot call "send" once a close message has been sent.')

    async def accept(self, subprotocol: str = None) -> None:
        if self.client_state == WebSocketState.CONNECTING:
            # If we haven't yet seen the 'connect' message, then wait for it first.
            await self.receive()
        accept_event = WebSocketAcceptEvent(
            type="websocket.accept", subprotocol=subprotocol, headers=()
        )
        await self.send(accept_event)

    def _raise_on_disconnect(self, message: ASGIReceiveEvent) -> None:
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message["code"])

    async def receive_text(self) -> str:
        assert self.application_state == WebSocketState.CONNECTED
        message = await self.receive()
        self._raise_on_disconnect(message)
        message_text = message.get("text")
        assert isinstance(message_text, str)
        return message_text

    async def receive_bytes(self) -> bytes:
        assert self.application_state == WebSocketState.CONNECTED
        message = await self.receive()
        self._raise_on_disconnect(message)
        message_bytes = message.get("bytes")
        assert isinstance(message_bytes, bytes)
        return message_bytes

    async def receive_json(self, mode: str = "text") -> typing.Any:
        assert mode in ["text", "binary"]
        assert self.application_state == WebSocketState.CONNECTED
        message = await self.receive()
        self._raise_on_disconnect(message)

        if mode == "text":
            text = message.get("text")
        else:
            message_bytes = message.get("bytes")
            assert isinstance(message_bytes, bytes)
            text = message_bytes.decode("utf-8")
        assert isinstance(text, str)
        return json.loads(text)

    async def iter_text(self) -> typing.AsyncIterator[str]:
        try:
            while True:
                yield await self.receive_text()
        except WebSocketDisconnect:
            pass

    async def iter_bytes(self) -> typing.AsyncIterator[bytes]:
        try:
            while True:
                yield await self.receive_bytes()
        except WebSocketDisconnect:
            pass

    async def iter_json(self) -> typing.AsyncIterator[typing.Any]:
        try:
            while True:
                yield await self.receive_json()
        except WebSocketDisconnect:
            pass

    async def send_text(self, data: str) -> None:
        send_event = WebSocketSendEvent(
            type="websocket.send",
            bytes=None,
            text=data,
        )
        await self.send(send_event)

    async def send_bytes(self, data: bytes) -> None:
        send_event = WebSocketSendEvent(
            type="websocket.send",
            bytes=data,
            text=None,
        )
        await self.send(send_event)

    async def send_json(self, data: typing.Any, mode: str = "text") -> None:
        assert mode in ["text", "binary"]
        text = json.dumps(data)
        if mode == "text":
            send_event = WebSocketSendEvent(
                type="websocket.send",
                bytes=None,
                text=text,
            )
            await self.send(send_event)
        else:
            send_event = WebSocketSendEvent(
                type="websocket.send",
                bytes=text.encode("utf-8"),
                text=None,
            )
            await self.send(send_event)

    async def close(self, code: int = 1000) -> None:
        close_event = WebSocketCloseEvent(
            type="websocket.close",
            code=code,
            reason=None,
        )
        await self.send(close_event)


class WebSocketClose:
    def __init__(self, code: int = 1000) -> None:
        self.code = code

    async def __call__(
        self, scope: WWWScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        close_event = WebSocketCloseEvent(
            type="websocket.close",
            code=self.code,
            reason=None,
        )
        await send(close_event)

import asyncio
import http
import inspect
import json
import queue
import threading
import typing
from urllib.parse import unquote

import http3
from starlette.datastructures import URL
from starlette.types import Message, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

ASGIInstance = typing.Callable[[Receive, Send], typing.Awaitable[None]]
ASGI2App = typing.Callable[[Scope], ASGIInstance]
ASGI3App = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]


def _get_reason_phrase(status_code: int) -> str:
    try:
        return http.HTTPStatus(status_code).phrase
    except ValueError:
        return ""


def _is_asgi3(app: typing.Union[ASGI2App, ASGI3App]) -> bool:
    if inspect.isclass(app):
        return hasattr(app, "__await__")
    elif inspect.isfunction(app):
        return asyncio.iscoroutinefunction(app)
    call = getattr(app, "__call__", None)
    return asyncio.iscoroutinefunction(call)


class _WrapASGI2:
    """
    Provide an ASGI3 interface onto an ASGI2 app.
    """

    def __init__(self, app: ASGI2App) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        instance = self.app(scope)
        await instance(receive, send)


class WebSocketTestSession:
    def __init__(self, app: ASGI3App, scope: Scope) -> None:
        self.app = app
        self.scope = scope
        self.accepted_subprotocol = None
        self._loop = asyncio.new_event_loop()
        self._receive_queue = queue.Queue()  # type: queue.Queue
        self._send_queue = queue.Queue()  # type: queue.Queue
        self._thread = threading.Thread(target=self._run)
        self.send({"type": "websocket.connect"})
        self._thread.start()
        message = self.receive()
        self._raise_on_close(message)
        self.accepted_subprotocol = message.get("subprotocol", None)

    def __enter__(self) -> "WebSocketTestSession":
        return self

    def __exit__(self, *args: typing.Any) -> None:
        self.close(1000)
        self._thread.join()
        while not self._send_queue.empty():
            message = self._send_queue.get()
            if isinstance(message, BaseException):
                raise message

    def _run(self) -> None:
        """
        The sub-thread in which the websocket session runs.
        """
        scope = self.scope
        receive = self._asgi_receive
        send = self._asgi_send
        try:
            self._loop.run_until_complete(self.app(scope, receive, send))
        except BaseException as exc:
            self._send_queue.put(exc)

    async def _asgi_receive(self) -> Message:
        while self._receive_queue.empty():
            await asyncio.sleep(0)
        return self._receive_queue.get()

    async def _asgi_send(self, message: Message) -> None:
        self._send_queue.put(message)

    def _raise_on_close(self, message: Message) -> None:
        if message["type"] == "websocket.close":
            raise WebSocketDisconnect(message.get("code", 1000))

    def send(self, message: Message) -> None:
        self._receive_queue.put(message)

    def send_text(self, data: str) -> None:
        self.send({"type": "websocket.receive", "text": data})

    def send_bytes(self, data: bytes) -> None:
        self.send({"type": "websocket.receive", "bytes": data})

    def send_json(self, data: typing.Any, mode: str = "text") -> None:
        assert mode in ["text", "binary"]
        text = json.dumps(data)
        if mode == "text":
            self.send({"type": "websocket.receive", "text": text})
        else:
            self.send({"type": "websocket.receive", "bytes": text.encode("utf-8")})

    def close(self, code: int = 1000) -> None:
        self.send({"type": "websocket.disconnect", "code": code})

    def receive(self) -> Message:
        message = self._send_queue.get()
        if isinstance(message, BaseException):
            raise message
        return message

    def receive_text(self) -> str:
        message = self.receive()
        self._raise_on_close(message)
        return message["text"]

    def receive_bytes(self) -> bytes:
        message = self.receive()
        self._raise_on_close(message)
        return message["bytes"]

    def receive_json(self, mode: str = "text") -> typing.Any:
        assert mode in ["text", "binary"]
        message = self.receive()
        self._raise_on_close(message)
        if mode == "text":
            text = message["text"]
        else:
            text = message["bytes"].decode("utf-8")
        return json.loads(text)


class TestClient(http3.Client):
    __test__ = False  # For pytest to not discover this up.

    def __init__(
        self,
        app: typing.Union[ASGI2App, ASGI3App],
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
    ) -> None:
        if _is_asgi3(app):
            self.app = typing.cast(ASGI3App, app)
        else:
            self.app = _WrapASGI2(typing.cast(ASGI2App, app))  #   type: ignore
        super().__init__(
            app=self.app,
            base_url=base_url,
            raise_app_exceptions=raise_server_exceptions,
        )

    def websocket_connect(
        self,
        url: str,
        subprotocols: typing.Sequence[str] = None,
        auth: typing.Callable = None,
        headers: dict = None,
        cookies: dict = None,
    ) -> typing.Any:
        url = self.base_url.join(url)
        cookies = self.merge_cookies(cookies=cookies)
        request = http3.Request(method="GET", url=url, cookies=cookies, headers=headers)

        auth = auth or self.auth
        if auth is not None:
            if isinstance(auth, tuple):
                auth = http3.auth.HTTPBasicAuth(username=auth[0], password=auth[1])
            request = auth(request)

        request.headers.setdefault("connection", "upgrade")
        request.headers.setdefault("sec-websocket-key", "testserver==")
        request.headers.setdefault("sec-websocket-version", "13")
        if subprotocols is not None:
            request.headers.setdefault(
                "sec-websocket-protocol", ", ".join(subprotocols)
            )

        scope = {
            "type": "websocket",
            "path": unquote(request.url.path),
            "root_path": "",
            "scheme": "wss" if request.url.is_ssl else "ws",
            "query_string": request.url.query.encode(),
            "headers": request.headers.raw,
            "client": ["testclient", 50000],
            "server": [request.url.host, request.url.port],
            "subprotocols": subprotocols,
        }
        return WebSocketTestSession(app=self.app, scope=scope)

    def __enter__(self) -> "TestClient":
        loop = asyncio.get_event_loop()
        self.send_queue = asyncio.Queue()  # type: asyncio.Queue
        self.receive_queue = asyncio.Queue()  # type: asyncio.Queue
        self.task = loop.create_task(self.lifespan())
        loop.run_until_complete(self.wait_startup())
        return self

    def __exit__(self, *args: typing.Any) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.wait_shutdown())

    async def lifespan(self) -> None:
        scope = {"type": "lifespan"}
        try:
            await self.app(scope, self.receive_queue.get, self.send_queue.put)
        finally:
            await self.send_queue.put(None)

    async def wait_startup(self) -> None:
        await self.receive_queue.put({"type": "lifespan.startup"})
        message = await self.send_queue.get()
        if message is None:
            self.task.result()
        assert message["type"] == "lifespan.startup.complete"

    async def wait_shutdown(self) -> None:
        await self.receive_queue.put({"type": "lifespan.shutdown"})
        message = await self.send_queue.get()
        if message is None:
            self.task.result()
        assert message["type"] == "lifespan.shutdown.complete"
        await self.task

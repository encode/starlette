import asyncio
import logging
import traceback
import typing
from types import TracebackType

from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send

STATE_TRANSITION_ERROR = "Got invalid state transition on lifespan protocol."


class LifespanMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        startup_handlers: typing.List[typing.Callable] = None,
        shutdown_handlers: typing.List[typing.Callable] = None,
    ):
        self.app = app
        self.startup_handlers = list(startup_handlers or [])
        self.shutdown_handlers = list(shutdown_handlers or [])

    def add_event_handler(self, event_type: str, func: typing.Callable) -> None:
        assert event_type in ("startup", "shutdown")

        if event_type == "startup":
            self.startup_handlers.append(func)
        else:
            assert event_type == "shutdown"
            self.shutdown_handlers.append(func)

    def on_event(self, event_type: str) -> typing.Callable:
        def decorator(func: typing.Callable) -> typing.Callable:
            self.add_event_handler(event_type, func)
            return func

        return decorator

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] == "lifespan":
            return LifespanHandle(
                self.app, scope, self.startup_handlers, self.shutdown_handlers
            )
        return self.app(scope)


class LifespanHandle:
    def __init__(
        self,
        app: ASGIApp,
        scope: Scope,
        startup_handlers: typing.List[typing.Callable],
        shutdown_handlers: typing.List[typing.Callable],
    ) -> None:
        self.inner = app(scope)
        self.startup_handlers = startup_handlers
        self.shutdown_handlers = shutdown_handlers
        self.send_buffer = asyncio.Queue()  # type: asyncio.Queue
        self.receive_buffer = asyncio.Queue()  # type: asyncio.Queue

    async def __call__(self, receive: Receive, send: Send) -> None:
        loop = asyncio.get_event_loop()
        inner_task = loop.create_task(
            self.inner(self.receive_buffer.get, self.send_buffer.put)
        )
        try:
            # Handle our own startup.
            message = await receive()
            assert message["type"] == "lifespan.startup"
            await self.startup()

            # Pass the message on to the next in the chain, and wait for the response.
            await self.receive_buffer.put(message)
            message = await self.send_buffer.get()
            assert message["type"] == "lifespan.startup.complete"
            await send({"type": "lifespan.startup.complete"})

            # Handle our own shutdown.
            message = await receive()
            assert message["type"] == "lifespan.shutdown"
            await self.shutdown()

            # Pass the message on to the next in the chain, and wait for the response.
            await self.receive_buffer.put(message)
            message = await self.send_buffer.get()
            assert message["type"] == "lifespan.shutdown.complete"
            await send({"type": "lifespan.shutdown.complete"})
        finally:
            await inner_task

    async def startup(self) -> None:
        for handler in self.startup_handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()

    async def shutdown(self) -> None:
        for handler in self.shutdown_handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()


class LifespanContext:
    def __init__(
        self, app: ASGIApp, startup_timeout: int = 10, shutdown_timeout: int = 10
    ) -> None:
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout
        self.startup_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        self.receive_queue = asyncio.Queue()  # type: asyncio.Queue
        self.asgi = app({"type": "lifespan"})  # type: ASGIInstance

    def __enter__(self) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self.run_lifespan())
        loop.run_until_complete(self.wait_startup())

    def __exit__(
        self,
        exc_type: typing.Type[BaseException],
        exc: BaseException,
        tb: TracebackType,
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.wait_shutdown())

    async def run_lifespan(self) -> None:
        try:
            await self.asgi(self.receive, self.send)
        finally:
            self.startup_event.set()
            self.shutdown_event.set()

    async def send(self, message: Message) -> None:
        if message["type"] == "lifespan.startup.complete":
            assert not self.startup_event.is_set(), STATE_TRANSITION_ERROR
            assert not self.shutdown_event.is_set(), STATE_TRANSITION_ERROR
            self.startup_event.set()
        else:
            assert message["type"] == "lifespan.shutdown.complete"
            assert self.startup_event.is_set(), STATE_TRANSITION_ERROR
            assert not self.shutdown_event.is_set(), STATE_TRANSITION_ERROR
            self.shutdown_event.set()

    async def receive(self) -> Message:
        return await self.receive_queue.get()

    async def wait_startup(self) -> None:
        await self.receive_queue.put({"type": "lifespan.startup"})
        await asyncio.wait_for(self.startup_event.wait(), timeout=self.startup_timeout)

    async def wait_shutdown(self) -> None:
        await self.receive_queue.put({"type": "lifespan.shutdown"})
        await asyncio.wait_for(
            self.shutdown_event.wait(), timeout=self.shutdown_timeout
        )

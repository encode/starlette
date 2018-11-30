import functools
import typing

import asyncpgsa

from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send


class DatabaseMiddleware:
    def __init__(self, app: ASGIApp, database_url: str) -> None:
        self.app = app
        self.database_url = database_url
        self.pool = None  # type: typing.Any

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] == "lifespan":
            return DatabaseLifespan(self.app, self, scope)
        return functools.partial(self.asgi, scope=scope)

    async def asgi(self, receive: Receive, send: Send, scope: Scope) -> None:
        conn = await self.pool.acquire()
        try:
            scope["db"] = conn
            inner = self.app(scope)
            await inner(receive, send)
        finally:
            await conn.close()

    async def startup(self) -> None:
        self.pool = await asyncpgsa.create_pool(self.database_url)

    async def shutdown(self) -> None:
        await self.pool.close()


class DatabaseLifespan:
    def __init__(
        self, app: ASGIApp, middleware: DatabaseMiddleware, scope: Scope
    ) -> None:
        self.inner = app(scope)
        self.middleware = middleware

    async def __call__(self, receive: Receive, send: Send) -> None:
        try:

            async def receiver() -> Message:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await self.middleware.startup()
                elif message["type"] == "lifespan.shutdown":
                    await self.middleware.shutdown()
                return message

            await self.inner(receiver, send)
        finally:
            self.middleware = None  # type: ignore

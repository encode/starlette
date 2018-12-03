import functools
import typing

import asyncpg

from starlette.drivers.postgres_asyncpg import PostgresBackend
from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send


class DatabaseMiddleware:
    def __init__(self, app: ASGIApp, database_url: str) -> None:
        self.app = app
        self.backend = PostgresBackend(database_url)

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] == "lifespan":
            return DatabaseLifespan(self.app, self, scope)
        scope["db"] = self.backend.new_session()
        return self.app(scope)

    async def startup(self) -> None:
        await self.backend.startup()

    async def shutdown(self) -> None:
        await self.backend.shutdown()


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

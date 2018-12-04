import functools
import typing

import asyncpg

from starlette.drivers.postgres_asyncpg import PostgresBackend
from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send


class DatabaseMiddleware:
    def __init__(
        self, app: ASGIApp, database_url: str, rollback_sessions: bool
    ) -> None:
        self.app = app
        self.backend = PostgresBackend(database_url)
        self.rollback_sessions = rollback_sessions

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] == "lifespan":
            return DatabaseLifespan(self.app, self, scope)
        return SessionManager(self.backend, self.rollback_sessions, self.app, scope)

    async def startup(self) -> None:
        await self.backend.startup()

    async def shutdown(self) -> None:
        await self.backend.shutdown()


class SessionManager:
    def __init__(
        self, backend: PostgresBackend, rollback: bool, app: ASGIApp, scope: Scope
    ) -> None:
        self.session = backend.session()
        self.rollback = rollback
        scope["db"] = self.session
        self.inner = app(scope)

    async def __call__(self, receive: Receive, send: Send) -> None:
        await self.inner(receive, send)


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

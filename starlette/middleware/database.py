import functools
import typing

import asyncpg

from starlette.database import DatabaseSession, DatabaseTransaction
from starlette.drivers.postgres_asyncpg import PostgresBackend
from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send


class DatabaseMiddleware:
    def __init__(
        self, app: ASGIApp, database_url: str, rollback_sessions: bool
    ) -> None:
        self.app = app
        self.backend = PostgresBackend(database_url)
        self.rollback_sessions = rollback_sessions
        self.session = None  # type: typing.Optional[DatabaseSession]
        self.transaction = None  # type: typing.Optional[DatabaseTransaction]

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] == "lifespan":
            return DatabaseLifespan(self.app, self, scope)

        if self.session is not None:
            session = self.session
        else:
            session = self.backend.session()  # pragma: no cover
        scope["db"] = session
        return self.app(scope)

    async def startup(self) -> None:
        await self.backend.startup()
        if self.rollback_sessions:
            self.session = self.backend.session()
            self.transaction = self.session.transaction()
            await self.transaction.start()

    async def shutdown(self) -> None:
        if self.rollback_sessions:
            assert self.session is not None
            assert self.transaction is not None
            await self.transaction.rollback()
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

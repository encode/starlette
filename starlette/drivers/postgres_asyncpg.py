import typing

import asyncpg
from sqlalchemy.dialects.postgresql import pypostgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql import ClauseElement

from starlette.database import DatabaseBackend, DatabaseSession, compile


class PostgresBackend(DatabaseBackend):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.dialect = self.get_dialect()
        self.pool = None

    def get_dialect(self) -> Dialect:
        dialect = pypostgresql.dialect(paramstyle="pyformat")

        dialect.implicit_returning = True
        dialect.supports_native_enum = True
        dialect.supports_smallserial = True  # 9.2+
        dialect._backslash_escapes = False
        dialect.supports_sane_multi_rowcount = True  # psycopg 2.0.9+
        dialect._has_native_hstore = True

        return dialect

    async def startup(self) -> None:
        self.pool = await asyncpg.create_pool(self.database_url)

    async def shutdown(self) -> None:
        assert self.pool is not None, "DatabaseBackend is not running"
        await self.pool.close()
        self.pool = None

    def new_session(self) -> "PostgresSession":
        assert self.pool is not None, "DatabaseBackend is not running"
        return PostgresSession(self.pool, self.dialect)


class PostgresSession(DatabaseSession):
    def __init__(self, pool: asyncpg.pool.Pool, dialect: Dialect):
        self.pool = pool
        self.dialect = dialect

    async def fetchall(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self.pool.acquire()
        try:
            return await conn.fetch(query, *args)
        finally:
            await self.pool.release(conn)

    async def fetchone(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self.pool.acquire()
        try:
            return await conn.fetchrow(query, *args)
        finally:
            await self.pool.release(conn)

    async def execute(self, query: ClauseElement) -> None:
        query, args = compile(query, dialect=self.dialect)

        conn = await self.pool.acquire()
        try:
            await conn.execute(query, *args)
        finally:
            await self.pool.release(conn)

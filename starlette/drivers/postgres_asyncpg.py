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
        self.transaction_stack = []

    async def fetchall(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self._get_connection()
        try:
            return await conn.fetch(query, *args)
        finally:
            await self._release_connection(conn)

    async def fetchone(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self._get_connection()
        try:
            return await conn.fetchrow(query, *args)
        finally:
            await self._release_connection(conn)

    async def execute(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self._get_connection()
        try:
            return await conn.execute(query, *args)
        finally:
            await self._release_connection(conn)

    def transaction(self):
        return PostgresTransaction(self.pool, self.transaction_stack)

    async def _get_connection(self) -> asyncpg.Connection:
        if self.transaction_stack:
            return self.transaction_stack[-1]._conn
        else:
            return await self.pool.acquire()

    async def _release_connection(self, conn):
        if not self.transaction_stack:
            await self.pool.release(conn)


class PostgresTransaction:
    def __init__(self, pool, transaction_stack):
        self.pool = pool
        self.transaction_stack = transaction_stack
        self._conn = None
        self._trans = None

    async def __aenter__(self):
        await self.start()

    async def __aexit__(self, extype, ex, tb):
        if extype is not None:
            await self.rollback()
        else:
            await self.commit()

    async def start(self):
        if self.transaction_stack:
            self._conn = self.transaction_stack[-1]._conn
        else:
            self._conn = await self.pool.acquire()
        self._trans = self._conn.transaction()
        await self._trans.start()
        self.transaction_stack.append(self)

    async def commit(self):
        transaction = self.transaction_stack.pop()
        assert transaction is self
        await self._trans.commit()
        if not self.transaction_stack:
            self.pool.release(self._conn)

    async def rollback(self):
        transaction = self.transaction_stack.pop()
        assert transaction is self
        await self._trans.rollback()
        if not self.transaction_stack:
            self.pool.release(self._conn)

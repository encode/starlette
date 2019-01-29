import typing
from types import TracebackType

from sqlalchemy.dialects.mysql import pymysql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql import ClauseElement

import aiomysql
from starlette.database.core import (
    DatabaseBackend,
    DatabaseSession,
    DatabaseTransaction,
    compile,
)
from starlette.datastructures import DatabaseURL


class MysqlBackend(DatabaseBackend):
    def __init__(self, database_url: typing.Union[str, DatabaseURL]) -> None:
        self.database_url = DatabaseURL(database_url)
        self.dialect = self.get_dialect()
        self.pool = None

    def get_dialect(self) -> Dialect:
        return pymysql.dialect(paramstyle="pyformat")

    async def startup(self) -> None:
        db = self.database_url
        self.pool = await aiomysql.create_pool(
            host=db.hostname,
            port=db.port,
            user=db.username,
            password=db.password,
            db=db.database,
        )

    async def shutdown(self) -> None:
        assert self.pool is not None, "DatabaseBackend is not running"
        self.pool.close()
        self.pool = None

    def session(self) -> "MysqlSession":
        assert self.pool is not None, "DatabaseBackend is not running"
        return MysqlSession(self.pool, self.dialect)


class MysqlSession(DatabaseSession):
    def __init__(self, pool: aiomysql.pool.Pool, dialect: Dialect):
        self.pool = pool
        self.dialect = dialect
        self.conn = None
        self.connection_holders = 0

    async def fetchall(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self.acquire_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, *args)
            return await cursor.fetchall()
        finally:
            await cursor.close()
            await self.release_connection()

    async def fetchone(self, query: ClauseElement) -> typing.Any:
        query, args = compile(query, dialect=self.dialect)

        conn = await self.acquire_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, *args)
            return await conn.fetchrow(query, *args)
        finally:
            await cursor.close()
            await self.release_connection()

    async def execute(self, query: ClauseElement) -> None:
        query, args = compile(query, dialect=self.dialect)

        conn = await self.acquire_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, *args)
        finally:
            await cursor.close()
            await self.release_connection()

    async def executemany(self, query: ClauseElement, values: list) -> None:
        conn = await self.acquire_connection()
        cursor = await conn.cursor()
        try:
            for item in values:
                single_query = query.values(item)
                single_query, args = compile(single_query, dialect=self.dialect)
                await cursor.execute(single_query, *args)
        finally:
            await cursor.close()
            await self.release_connection()

    def transaction(self) -> DatabaseTransaction:
        return MysqlTransaction(self)

    async def acquire_connection(self) -> aiomysql.Connection:
        """
        Either acquire a connection from the pool, or return the
        existing connection. Must be followed by a corresponding
        call to `release_connection`.
        """
        self.connection_holders += 1
        if self.conn is None:
            self.conn = await self.pool.acquire()
        return self.conn

    async def release_connection(self) -> None:
        self.connection_holders -= 1
        if self.connection_holders == 0:
            await self.pool.release(self.conn)
            self.conn = None


class MysqlTransaction(DatabaseTransaction):
    def __init__(self, session: MysqlSession):
        self.session = session

    async def __aenter__(self) -> None:
        await self.start()

    async def __aexit__(
        self,
        exc_type: typing.Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

    async def start(self) -> None:
        self.conn = await self.session.acquire_connection()
        await self.conn.begin()

    async def commit(self) -> None:
        await self.conn.commit()
        await self.session.release_connection()

    async def rollback(self) -> None:
        await self.conn.rollback()
        await self.session.release_connection()

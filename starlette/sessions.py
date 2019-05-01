import abc
import uuid
from typing import Optional

try:
    import aioredis
except ImportError:  # pragma: nocover
    aioredis = None

try:
    import databases
except ImportError:  # pragma: nocover
    databases = None

try:
    import aiomcache
except ImportError:  # pragma: nocover
    aiomcache = None


class SessionNotFoundError(Exception):
    pass


class SessionBackend(abc.ABC):
    @abc.abstractmethod
    async def read(self, session_id: str) -> Optional[str]:  # pragma: nocover
        ...

    @abc.abstractmethod
    async def write(self, session_id: str, data: str) -> str:  # pragma: nocover
        ...

    @abc.abstractmethod
    async def remove(self, session_id: str) -> None:  # pragma: nocover
        ...

    async def exists(self, session_id: str) -> bool:
        return await self.read(session_id) is not None

    def generate_id(self) -> str:
        """ Generate a new session id. """
        return str(uuid.uuid4())


class InMemoryBackend(SessionBackend):
    def __init__(self) -> None:
        self._data: dict = {}

    async def read(self, session_id: str) -> Optional[str]:
        return self._data.get(session_id, None)

    async def write(self, session_id: str, data: str) -> str:
        self._data[session_id] = data
        return session_id

    async def remove(self, session_id: str) -> None:
        del self._data[session_id]


class CookieBackend(SessionBackend):
    async def read(self, session_id: str) -> Optional[str]:
        """ A session_id is a signed session value. """
        return session_id

    async def write(self, session_id: str, data: str) -> str:
        """ The data is a session id in this backend. """
        return data

    async def remove(self, session_id: str) -> None:
        """ Session data stored on client side - no way to remove it. """

    async def exists(self, session_id: str) -> bool:
        return False


class RedisBackend(SessionBackend):
    def __init__(self, client: "aioredis.Redis") -> None:
        assert aioredis, "aioredis must be installed to use RedisBackend"

        self.redis = client

    async def read(self, session_id: str) -> Optional[str]:
        return await self.redis.get(session_id)

    async def write(self, session_id: str, data: str) -> str:
        await self.redis.set(session_id, data)
        return session_id

    async def remove(self, session_id: str) -> None:
        await self.redis.delete(session_id)


class MemcachedBackend(SessionBackend):
    def __init__(self, client: "aiomcache.Client") -> None:
        assert aiomcache, "aiomcache must be installed to use MemcachedBackend"

        self.client = client

    async def read(self, session_id: str) -> Optional[str]:
        data = await self.client.get(session_id.encode("utf-8"))
        if data:
            return data.decode("utf-8")
        return None

    async def write(self, session_id: str, data: str) -> str:
        await self.client.set(session_id.encode("utf-8"), data.encode("utf-8"))
        return session_id

    async def remove(self, session_id: str) -> None:
        await self.client.delete(session_id.encode("utf-8"))


class DatabaseBackend(SessionBackend):
    def __init__(
        self,
        database: "databases.Database",
        table: str = "sessions",
        id_column: str = "id",
        data_column: str = "data",
    ) -> None:
        assert databases, "databases must be installed to use DatabaseBackend"

        self.database = database
        self.table = table
        self.id_column = id_column
        self.data_column = data_column
        self._exists = False

    async def read(self, session_id: str) -> Optional[str]:
        sql = (
            f"SELECT {self.data_column} "
            f"FROM {self.table} "
            f"WHERE {self.id_column} = :id"
        )
        data = await self.database.fetch_val(sql, {"id": session_id}, self.data_column)
        if data:
            self._exists = True
        return data

    async def write(self, session_id: str, data: str) -> str:
        if self._exists:
            await self._update(session_id, data)
        else:
            await self._insert(session_id, data)

        return session_id

    async def remove(self, session_id: str) -> None:
        sql = "DELETE FROM %s WHERE %s = :id" % (self.table, self.id_column)
        params = {"id": session_id}
        await self.database.execute(sql, params)

    async def _update(self, session_id: str, data: str) -> None:
        params = {"id": session_id, "data": data}
        sql = "UPDATE %s SET %s = :data WHERE %s = :id " % (
            self.table,
            self.data_column,
            self.id_column,
        )
        await self.database.execute(sql, params)

    async def _insert(self, session_id: str, data: str) -> None:
        params = {"id": session_id, "data": data}
        sql = "INSERT INTO %s (%s, %s) VALUES(:id, :data)" % (
            self.table,
            self.id_column,
            self.data_column,
        )
        await self.database.execute(sql, params)

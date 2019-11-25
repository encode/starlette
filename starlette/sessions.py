import abc
import json
import typing
import uuid
from base64 import b64encode

from itsdangerous import TimestampSigner, BadTimeSignature, SignatureExpired

from starlette.datastructures import Secret

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


class Storage(abc.ABC):
    @abc.abstractmethod
    async def read(self, session_id: str) -> typing.MutableMapping[str, typing.Any]:
        raise NotImplementedError()

    @abc.abstractmethod
    async def write(self, session_id: str, data: typing.MutableMapping) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    async def remove(self, session_id: str) -> None:
        raise NotImplementedError()

    async def generate_id(self) -> str:
        return str(uuid.uuid4())


class CookieStorage(Storage):
    def __init__(self, secret_key: typing.Union[str, Secret], max_age: int):
        self._signer = TimestampSigner(secret_key)
        self._max_age = max_age

    async def read(self, session_id: str) -> typing.MutableMapping:
        """ A session_id is a signed session value. """
        try:
            return self._signer.unsign(session_id, max_age=self._max_age)
        except (BadTimeSignature, SignatureExpired):
            return {}

    async def write(self, session_id: str, data: typing.MutableMapping) -> str:
        """ The data is a session id in this backend. """
        data = b64encode(json.dumps(data).encode("utf-8"))
        return self._signer.sign(data).decode("utf-8")

    async def remove(self, session_id: str) -> None:
        """ Session data stored on client side - no way to remove it. """

    async def exists(self, session_id: str) -> bool:
        return False


class Session(typing.MutableMapping[str, typing.Any]):
    def __init__(self, storage: Storage, session_id: str = None) -> None:
        self._data = {}
        self._storage = storage
        self.session_id = session_id
        self._is_modified = False

    @property
    def is_empty(self) -> bool:
        return len(self.keys()) == 0

    @property
    def is_modified(self) -> bool:
        pass

    async def load(self) -> None:
        self._data = await self._storage.read(self.session_id)

    async def persist(self) -> str:
        if self.session_id is None:
            self.session_id = await self._storage.generate_id()
        await self._storage.write(self.session_id, self._data)
        return self.session_id

    def keys(self) -> typing.KeysView[str]:
        return self._data.keys()

    def values(self) -> typing.ValuesView[typing.Any]:
        return self._data.values()

    def items(self) -> typing.ItemsView[str, typing.Any]:
        return self._data.items()

    def pop(self, key: str, default: typing.Any = None) -> typing.Any:
        self._is_modified = True
        return self._data.pop(key, default)

    def get(self, name: str, default: typing.Any = None) -> typing.Any:
        return self._data.get(name, default)

    def setdefault(self, key: str, default: typing.Any) -> None:
        self._is_modified = True
        self._data.setdefault(key, default)

    def clear(self) -> None:
        self._is_modified = True
        self._data.clear()

    def update(self, *args, **kwargs) -> None:
        self._is_modified = True
        self._data.update(*args, **kwargs)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __setitem__(self, key: str, value: typing.Any) -> None:
        self._is_modified = True
        self._data[key] = value

    def __getitem__(self, key: str) -> typing.Any:
        return self._data[key]

    def __delitem__(self, key: str) -> None:
        self._is_modified = True
        del self._data[key]


class InMemoryBackend(SessionBackend):
    def __init__(self) -> None:
        self._data: dict = {}

    async def read(self, session_id: str) -> typing.Optional[str]:
        return self._data.get(session_id, None)

    async def write(self, session_id: str, data: str) -> str:
        self._data[session_id] = data
        return session_id

    async def remove(self, session_id: str) -> None:
        del self._data[session_id]


class RedisBackend(SessionBackend):
    def __init__(self, client: "aioredis.Redis") -> None:
        assert aioredis, "aioredis must be installed to use RedisBackend"

        self.redis = client

    async def read(self, session_id: str) -> typing.Optional[str]:
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

    async def read(self, session_id: str) -> typing.Optional[str]:
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

    async def read(self, session_id: str) -> typing.Optional[str]:
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

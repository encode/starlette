from unittest import mock

import pytest

from starlette.sessions import (
    CookieBackend,
    DatabaseBackend,
    InMemoryBackend,
    MemcachedBackend,
    RedisBackend,
)


class _Store:
    def __init__(self):
        self._store = {}

    async def set(self, key, value):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key, None)

    async def delete(self, key):
        del self._store[key]


@pytest.fixture()
def in_memory():
    return InMemoryBackend()


@pytest.fixture()
def cookie():
    return CookieBackend()


@pytest.fixture()
def memcached():
    store = _Store()
    client = mock.MagicMock()
    client.set.side_effect = store.set
    client.get.side_effect = store.get
    client.delete.side_effect = store.delete
    with mock.patch("starlette.sessions.aiomcache", object()):
        return MemcachedBackend(client)


@pytest.fixture()
def redis():
    store = _Store()
    client = mock.MagicMock()
    client.set.side_effect = store.set
    client.get.side_effect = store.get
    client.delete.side_effect = store.delete
    with mock.patch("starlette.sessions.aioredis", object()):
        return RedisBackend(client)


def test_generate_id(in_memory):
    new_id = in_memory.generate_id()
    assert isinstance(new_id, str)


class TestInMemoryBackend:
    @pytest.mark.asyncio
    async def test_read_write(self, in_memory):
        new_id = await in_memory.write("id", "data")
        assert new_id == "id"
        assert await in_memory.read("id") == "data"

    @pytest.mark.asyncio
    async def test_remove(self, in_memory):
        await in_memory.write("id", "data")
        await in_memory.remove("id")
        assert await in_memory.read("id") is None

    @pytest.mark.asyncio
    async def test_exists(self, in_memory):
        await in_memory.write("id", "data")
        assert await in_memory.exists("id") is True
        assert await in_memory.exists("other id") is False


class TestCookieBackend:
    @pytest.mark.asyncio
    async def test_read_write(self, cookie):
        new_id = await cookie.write("id", "data")
        assert new_id == "data"
        assert await cookie.read("id") == "id"

    @pytest.mark.asyncio
    async def test_remove(self, cookie):
        await cookie.remove("id")

    @pytest.mark.asyncio
    async def test_exists(self, cookie):
        assert await cookie.exists("id") is False


class TestRedisBackend:
    @pytest.mark.asyncio
    async def test_requires_aioredis(self):
        with mock.patch("starlette.sessions.aioredis", None):
            with pytest.raises(AssertionError):
                RedisBackend(None)

    @pytest.mark.asyncio
    async def test_read_write(self, redis):
        new_id = await redis.write("id", "data")
        assert new_id == "id"
        assert await redis.read("id") == "data"

    @pytest.mark.asyncio
    async def test_remove(self, redis):
        await redis.write("id", "data")
        await redis.remove("id")
        assert await redis.read("id") is None

    @pytest.mark.asyncio
    async def test_exists(self, redis):
        await redis.write("id", "data")
        assert await redis.exists("id") is True
        assert await redis.exists("other id") is False


class TestMemcachedBackend:
    @pytest.mark.asyncio
    async def test_requires_aiomcache(self):
        with mock.patch("starlette.sessions.aiomcache", None):
            with pytest.raises(AssertionError):
                MemcachedBackend(None)

    @pytest.mark.asyncio
    async def test_read_write(self, memcached):
        new_id = await memcached.write("id", "data")
        assert new_id == "id"
        assert await memcached.read("id") == "data"

    @pytest.mark.asyncio
    async def test_remove(self, memcached):
        await memcached.write("id", "data")
        await memcached.remove("id")
        assert await memcached.read("id") is None

    @pytest.mark.asyncio
    async def test_exists(self, memcached):
        await memcached.write("id", "data")
        assert await memcached.exists("id") is True
        assert await memcached.exists("other id") is False


class TestDatabaseBackend:
    @pytest.mark.asyncio
    async def test_requires_databases(self):
        with mock.patch("starlette.sessions.databases", None):
            with pytest.raises(AssertionError):
                DatabaseBackend(None)

    @pytest.mark.asyncio
    async def test_read(self):
        async def _fetch(*args):
            return "data"

        client = mock.MagicMock()
        client.fetch_val.side_effect = _fetch

        databases = DatabaseBackend(client)
        assert await databases.read("id") == "data"
        assert databases._exists

    @pytest.mark.asyncio
    async def test_read_data_not_exists(self):
        async def _fetch(*args):
            return None

        client = mock.MagicMock()
        client.fetch_val.side_effect = _fetch

        databases = DatabaseBackend(client)
        assert await databases.read("id") is None
        assert not databases._exists

    @pytest.mark.asyncio
    async def test_write_updates(self):
        used_query = None

        async def _fn(query, *args):
            nonlocal used_query
            used_query = query

        client = mock.MagicMock()
        client.execute.side_effect = _fn
        databases = DatabaseBackend(client)
        databases._exists = True
        await databases.write("id", "data")
        assert "UPDATE" in used_query

    @pytest.mark.asyncio
    async def test_write_inserts(self):
        used_query = None

        async def _fn(query, *args):
            nonlocal used_query
            used_query = query

        client = mock.MagicMock()
        client.execute.side_effect = _fn
        databases = DatabaseBackend(client)
        databases._exists = False
        await databases.write("id", "data")
        assert "INSERT" in used_query

    @pytest.mark.asyncio
    async def test_remove(self):
        used_query = None

        async def _fn(query, *args):
            nonlocal used_query
            used_query = query

        client = mock.MagicMock()
        client.execute.side_effect = _fn
        databases = DatabaseBackend(client)
        await databases.remove("id")
        assert "DELETE" in used_query

    @pytest.mark.asyncio
    async def test_exists(self):
        async def _fn(query, params, *ars):
            if params["id"] == "id":
                return "data"
            return None

        client = mock.MagicMock()
        client.fetch_val.side_effect = _fn
        databases = DatabaseBackend(client)
        assert await databases.exists("id") is True
        assert await databases.exists("other id") is False

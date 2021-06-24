import pytest

from starlette.sessions import CookieBackend, InMemoryBackend, Session, SessionNotLoaded


@pytest.fixture()
def in_memory():
    return InMemoryBackend()


@pytest.fixture()
def cookie():
    return CookieBackend("key", 14)


@pytest.fixture()
def in_memory_session(in_memory):
    session = Session(in_memory)
    session.is_loaded = True
    return session


@pytest.fixture()
def session_payload():
    return {"key": "value"}


# cookie backend


@pytest.mark.asyncio
async def test_cookie_read_write(cookie, session_payload):
    new_id = await cookie.write(session_payload, "session_id")
    assert await cookie.read(new_id) == session_payload


@pytest.mark.asyncio
async def test_cookie_remove(cookie):
    await cookie.remove("session_id")


@pytest.mark.asyncio
async def test_cookie_exists(cookie):
    assert await cookie.exists("session_id") is False


@pytest.mark.asyncio
async def test_cookie_generate_id(cookie):
    new_id = await cookie.generate_id()
    assert isinstance(new_id, str)


# in memory backend


@pytest.mark.asyncio
async def test_in_memory_read_write(in_memory, session_payload):
    new_id = await in_memory.write(session_payload, "session_id")
    assert new_id == "session_id"
    assert await in_memory.read("session_id") == session_payload


@pytest.mark.asyncio
async def test_in_memory_remove(in_memory, session_payload):
    await in_memory.write(session_payload, "session_id")
    await in_memory.remove("session_id")
    assert await in_memory.exists("session_id") is False


@pytest.mark.asyncio
async def test_in_memory_exists(in_memory, session_payload):
    await in_memory.write(session_payload, "session_id")
    assert await in_memory.exists("session_id") is True
    assert await in_memory.exists("other id") is False


@pytest.mark.asyncio
async def test_in_memory_generate_id(in_memory):
    new_id = await in_memory.generate_id()
    assert isinstance(new_id, str)


def test_session_is_empty(in_memory_session):
    assert in_memory_session.is_empty is True

    in_memory_session["key"] = "value"
    assert in_memory_session.is_empty is False


def test_session_is_modified(in_memory_session):
    assert in_memory_session.is_modified is False

    in_memory_session["key"] = "value"
    assert in_memory_session.is_modified is True


# session


@pytest.mark.asyncio
async def test_session_load(in_memory, session_payload):
    await in_memory.write(session_payload, "session_id")

    session = Session(in_memory, "session_id")
    await session.load()
    assert session.items() == session_payload.items()


@pytest.mark.asyncio
async def test_session_load_with_new_session(in_memory, session_payload):
    session = Session(in_memory)
    await session.load()
    assert len(session.keys()) == 0


@pytest.mark.asyncio
async def test_session_subsequent_load(in_memory):
    """It should return the cached data on any sequential call to load()."""
    await in_memory.write(dict(key="value"), "session_id")

    session = Session(in_memory, "session_id")
    await session.load()

    assert "key" in session

    # add key2 to session. this value should survive the second load() call
    session["key2"] = "value2"
    await session.load()

    assert "key" in session
    assert "key2" in session


@pytest.mark.asyncio
async def test_session_persist(in_memory):
    session = Session(in_memory, "session_id")
    await session.load()
    session["key"] = "value"
    new_id = await session.persist()

    # session ID should no change when was passed via arguments
    assert new_id == "session_id"

    assert in_memory.data == {"session_id": {"key": "value"}}


@pytest.mark.asyncio
async def test_session_persist_generates_id(in_memory, in_memory_session):
    async def _generate_id():
        return "new_session_id"

    in_memory.generate_id = _generate_id
    await in_memory_session.persist()
    assert in_memory_session.session_id == "new_session_id"


@pytest.mark.asyncio
async def test_session_delete(in_memory):
    await in_memory.write({}, "session_id")

    session = Session(in_memory, "session_id")
    await session.load()
    session["key"] = "value"
    await session.delete()

    assert await in_memory.exists("session_id") is False
    assert session.is_modified is True
    assert session.is_empty is True

    # it shouldn't fail on non-persisted session
    session = Session(in_memory)
    await session.load()
    await session.delete()

    assert session.is_empty is True
    assert session.is_modified is False


@pytest.mark.asyncio
async def test_session_flush(in_memory):
    await in_memory.write({"key": "value"}, "session_id")

    session = Session(in_memory, "session_id")
    await session.load()
    new_id = await session.flush()
    assert new_id == session.session_id
    assert new_id != "session_id"
    assert session.is_modified is True
    assert session.is_empty is True

    # it shouldn't fail on non-persisted session
    session = Session(in_memory)
    await session.load()
    await session.flush()
    assert session.is_modified is True
    assert session.is_empty is True


@pytest.mark.asyncio
async def test_session_regenerate_id(in_memory):
    session = Session(in_memory, "session_id")
    new_id = await session.regenerate_id()
    assert session.session_id == new_id
    assert session.session_id != "session_id"
    assert session.is_modified is True


def test_session_keys(in_memory_session):
    in_memory_session["key"] = True
    assert list(in_memory_session.keys()) == ["key"]


def test_session_values(in_memory_session):
    in_memory_session["key"] = "value"
    assert list(in_memory_session.values()) == ["value"]


def test_session_items(in_memory_session):
    in_memory_session["key"] = "value"
    in_memory_session["key2"] = "value2"
    assert list(in_memory_session.items()) == [
        ("key", "value"),
        ("key2", "value2"),
    ]


def test_session_pop(in_memory_session):
    in_memory_session["key"] = "value"
    in_memory_session.pop("key")
    assert "key" not in in_memory_session
    assert in_memory_session.is_modified


def test_session_get(in_memory_session):
    in_memory_session["key"] = "value"
    assert in_memory_session.get("key") == "value"
    assert in_memory_session.get("key2", "miss") == "miss"
    assert in_memory_session.get("key3") is None


def test_session_setdefault(in_memory_session):
    in_memory_session.setdefault("key", "value")
    assert in_memory_session.get("key") == "value"
    assert in_memory_session.is_modified is True


def test_session_clear(in_memory_session):
    in_memory_session["key"] = "value"
    in_memory_session.clear()
    assert in_memory_session.is_empty is True
    assert in_memory_session.is_modified is True


def test_session_update(in_memory_session):
    in_memory_session.update({"key": "value"})
    assert "key" in in_memory_session
    assert in_memory_session.is_modified is True


def test_session_setitem_and_contains(in_memory_session):
    # set item
    in_memory_session["key"] = "value"  # __setitem__
    assert "key" in in_memory_session  # __contain__
    assert in_memory_session.is_modified is True


def test_session_getitem(in_memory_session):
    in_memory_session["key"] = "value"  # __getitem__
    assert in_memory_session["key"] == "value"


def test_session_delitem(in_memory_session):
    in_memory_session["key"] = "value"
    del in_memory_session["key"]  # __delitem__
    assert "key" not in in_memory_session


def test_session_denies_access_if_not_loaded():
    session = Session(in_memory)
    with pytest.raises(SessionNotLoaded):
        session.data.keys()

    with pytest.raises(SessionNotLoaded):
        session["key"] = "value"

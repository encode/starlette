from __future__ import annotations
import os
from pathlib import Path
from typing import Any

import pytest

from starlette.config import Config, Environ, EnvironError
from starlette.datastructures import URL, Secret


def is_str(x: list[str]) -> None:
    ...


def is_bool(x: list[bool]) -> None:
    ...


def is_int(x: list[int]) -> None:
    ...


def is_bool_or_none(x: list[bool | None]) -> None:
    ...


def is_str_or_none(x: list[str | None]) -> None:
    ...


def is_bool_or_str(x: list[bool | str]) -> None:
    ...


def test_config_types() -> None:
    config = Config(environ={"SIMPLE_KEY": "some_str_value", "BOOL_KEY": "true"})
    SIMPLE_KEY = config("SIMPLE_KEY")
    is_str([SIMPLE_KEY])
    BOOL_KEY = config("BOOL_KEY", cast=bool)
    is_bool([BOOL_KEY])
    BOOL_OR_NONE_KEY = config("BOOL_OR_NONE_KEY", cast=bool, default=None)
    is_bool_or_none([BOOL_OR_NONE_KEY])

    STR_OR_STR_KEY = config("STR_OR_STR_KEY", cast=str, default="hello")
    is_str([STR_OR_STR_KEY])
    STR_OR_NONE_KEY = config("STR_OR_NONE_KEY", default=None)
    is_str_or_none([STR_OR_NONE_KEY])

    BOOL_DEFAULT = config("BOOL_DEFAULT", cast=bool, default=False)
    is_bool([BOOL_DEFAULT])

    def cast_to_int(v: Any) -> int:
        return int(v)

    DEFAULTED_BOOL_TYPE = config("DEFAULTED_BOOL_TYPE", cast=int, default=True)
    is_int([DEFAULTED_BOOL_TYPE])

    # starlette Config will call the cast function on default and convert the bool to int.
    # We don't support this in
    DEFAULTED_BOOL_FUNC = config("DEFAULTED_BOOL_FUNC", cast=cast_to_int, default=True)  # type: ignore [arg-type]
    is_int([DEFAULTED_BOOL_FUNC])

    # We raise a ValueError when the string value can't be parsed into a bool
    with pytest.raises(ValueError):
        _ = config("BOOL_OR_STR_KEY", cast=bool, default="hello")  # type: ignore [arg-type]


def test_config(tmpdir, monkeypatch):
    path = os.path.join(tmpdir, ".env")
    with open(path, "w") as file:
        file.write("# Do not commit to source control\n")
        file.write("DATABASE_URL=postgres://user:pass@localhost/dbname\n")
        file.write("REQUEST_HOSTNAME=example.com\n")
        file.write("SECRET_KEY=12345\n")
        file.write("BOOL_AS_INT=0\n")
        file.write("\n")
        file.write("\n")

    config = Config(path, environ={"DEBUG": "true"})

    def cast_to_int(v) -> int:
        return int(v)

    DEBUG = config("DEBUG", cast=bool)
    DATABASE_URL = config("DATABASE_URL", cast=URL)
    REQUEST_TIMEOUT = config("REQUEST_TIMEOUT", cast=int, default=10)
    REQUEST_HOSTNAME = config("REQUEST_HOSTNAME")
    MAIL_HOSTNAME = config("MAIL_HOSTNAME", default=None)
    SECRET_KEY = config("SECRET_KEY", cast=Secret)
    UNSET_SECRET = config("UNSET_SECRET", cast=Secret, default=None)
    EMPTY_SECRET = config("EMPTY_SECRET", cast=Secret, default="")
    assert config("BOOL_AS_INT", cast=bool) is False
    assert config("BOOL_AS_INT", cast=cast_to_int) == 0
    assert config("DEFAULTED_BOOL", cast=cast_to_int, default=True) == 1

    assert DEBUG is True
    assert DATABASE_URL.path == "/dbname"
    assert DATABASE_URL.password == "pass"
    assert DATABASE_URL.username == "user"
    assert REQUEST_TIMEOUT == 10
    assert REQUEST_HOSTNAME == "example.com"
    assert MAIL_HOSTNAME is None
    assert repr(SECRET_KEY) == "Secret('**********')"
    assert str(SECRET_KEY) == "12345"
    assert bool(SECRET_KEY)
    assert not bool(EMPTY_SECRET)
    assert not bool(UNSET_SECRET)

    with pytest.raises(KeyError):
        config.get("MISSING")

    with pytest.raises(ValueError):
        config.get("DEBUG", cast=int)

    with pytest.raises(ValueError):
        config.get("REQUEST_HOSTNAME", cast=bool)

    config = Config(Path(path))
    REQUEST_HOSTNAME = config("REQUEST_HOSTNAME")
    assert REQUEST_HOSTNAME == "example.com"

    config = Config()
    monkeypatch.setenv("STARLETTE_EXAMPLE_TEST", "123")
    monkeypatch.setenv("BOOL_AS_INT", "1")
    assert config.get("STARLETTE_EXAMPLE_TEST", cast=int) == 123
    assert config.get("BOOL_AS_INT", cast=bool) is True

    monkeypatch.setenv("BOOL_AS_INT", "2")
    with pytest.raises(ValueError):
        config.get("BOOL_AS_INT", cast=bool)


def test_environ():
    environ = Environ()

    # We can mutate the environ at this point.
    environ["TESTING"] = "True"
    environ["GONE"] = "123"
    del environ["GONE"]

    # We can read the environ.
    assert environ["TESTING"] == "True"
    assert "GONE" not in environ

    # We cannot mutate these keys now that we've read them.
    with pytest.raises(EnvironError):
        environ["TESTING"] = "False"

    with pytest.raises(EnvironError):
        del environ["GONE"]

    # Test coverage of abstract methods for MutableMapping.
    environ = Environ()
    assert list(iter(environ)) == list(iter(os.environ))
    assert len(environ) == len(os.environ)

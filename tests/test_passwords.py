from unittest import mock

import pytest

from starlette.passwords import (
    Argon2PasswordHasher,
    BCryptPasswordHasher,
    PasswordChecker,
    PasswordHasher,
    PBKDF2PasswordHasher,
    PlainPasswordHasher,
)

try:
    import bcrypt
except ImportError:  # pragma: nocover
    bcrypt = None

try:
    import argon2
except ImportError:  # pragma: nocover
    argon2 = None


def test_generic_password_hasher():
    class _Child(PasswordHasher):
        async def check(self, password: str, encoded: str) -> bool:
            pass  # pragma: nocover

        async def make(self, password: str, salt: str = None, **kwargs) -> str:
            pass  # pragma: nocover

    hasher = _Child()
    assert len(hasher.generate_salt(4)) == 4
    assert len(hasher.generate_salt(8)) == 8

    with pytest.raises(ValueError):
        hasher.generate_salt(0)

    with pytest.raises(ValueError):
        hasher.generate_salt(-1)


@pytest.mark.asyncio
async def test_plain_hasher():
    password = "pàsšўoЯd"
    invalid_password = "pàsšўord"
    hasher = PlainPasswordHasher()
    hashed = await hasher.make(password)
    assert hasher.algorithm in hashed
    assert await hasher.check(password, hashed)
    assert not await hasher.check(invalid_password, hashed)


@pytest.mark.asyncio
async def test_pbkdf2_hasher():
    salt = "salt"
    password = "pàsšўoЯd"
    invalid_password = "pàsšўord"
    rounds = 150000
    hasher = PBKDF2PasswordHasher()
    ref = "pbkdf2_sha256$150000$salt$sLxQyeJXlgmnc/aDxFypP9iHjIYKl9RBxx85G3gn7ZA="
    hashed = await hasher.make(password, salt, rounds)
    assert hashed == ref
    assert hasher.algorithm in hashed
    assert str(rounds) in hashed
    assert salt in hashed
    assert await hasher.check(password, hashed)
    assert not await hasher.check(invalid_password, hashed)


@pytest.mark.skipif(not bcrypt, reason="bcrypt is not installed")
@pytest.mark.asyncio
async def test_bcrypt_hasher():
    password = "pàsšўoЯd"
    invalid_password = "pàsšўord"
    hasher = BCryptPasswordHasher()
    salt = hasher.generate_salt()
    hashed = await hasher.make(password, salt)
    assert hasher.algorithm in hashed
    assert salt in hashed
    assert await hasher.check(password, hashed)
    assert not await hasher.check(invalid_password, hashed)

    with mock.patch("starlette.passwords.bcrypt", None):
        with pytest.raises(AssertionError):
            BCryptPasswordHasher()


@pytest.mark.skipif(not argon2, reason="argon2 is not installed")
@pytest.mark.asyncio
async def test_argon2_hasher():
    salt = "saltsaltsalt"
    password = "pàsšўoЯd"
    invalid_password = "pàsšўord"
    hasher = Argon2PasswordHasher()
    hashed = await hasher.make(password, salt)
    assert hasher.algorithm in hashed
    assert await hasher.check(password, hashed)
    assert not await hasher.check(invalid_password, hashed)

    with mock.patch("starlette.passwords.argon2", None):
        with pytest.raises(AssertionError):
            Argon2PasswordHasher()


class TestPasswordChecker:
    def test_requires_hashers(self):
        with pytest.raises(AssertionError):
            PasswordChecker([])

    @pytest.mark.asyncio
    async def test_looksup_hashers(self):
        # this set requires password update
        hashers = [PBKDF2PasswordHasher(), PlainPasswordHasher()]
        hashed = "plain$password"
        checker = PasswordChecker(hashers)
        assert await checker.check("password", hashed)
        assert not await checker.check("invalid_password", hashed)
        assert checker.requires_update

        # this set does not require the password update
        # because the default (the first) hasher confirms the password
        hashed = "plain$password"
        hashers = [PlainPasswordHasher(), PBKDF2PasswordHasher()]
        checker = PasswordChecker(hashers)
        assert not await checker.check("invalid_password", hashed)
        assert not checker.requires_update

        # this has to fail as no hashers can verify the password
        hashed = "unsupported$password"
        hashers = [PlainPasswordHasher(), PBKDF2PasswordHasher()]
        checker = PasswordChecker(hashers)
        assert not await checker.check("password", hashed)

    def test_requires_update(self):
        checker = PasswordChecker([PlainPasswordHasher()])
        with pytest.raises(ValueError):
            checker.requires_update

    @pytest.mark.asyncio
    async def test_make(self):
        checker = PasswordChecker([PlainPasswordHasher(), PBKDF2PasswordHasher()])
        hashed = await checker.make("password")
        assert hashed == "plain$password"

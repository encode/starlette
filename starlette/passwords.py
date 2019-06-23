import abc
import base64
import binascii
import hashlib
import hmac
import random
from typing import Any, Callable, Optional, Sequence

from starlette.concurrency import run_in_threadpool

try:
    import argon2
except ImportError:  # pragma: nocover
    argon2 = None

try:
    import bcrypt
except ImportError:  # pragma: nocover
    bcrypt = None

ALNUM_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class PasswordHasher(abc.ABC):
    algorithm: str = ""

    @abc.abstractmethod
    async def check(self, password: str, encoded: str) -> bool:
        raise NotImplementedError()  # pragma: nocover

    @abc.abstractmethod
    async def make(self, password: str, salt: str = None, **kwargs: Any) -> str:
        raise NotImplementedError()  # pragma: nocover

    def generate_salt(self, length: int = 8) -> str:
        if length <= 0:
            raise ValueError("Salt length must be greater than zero.")
        randomizer = random.SystemRandom()
        randomizer.seed()
        return "".join(randomizer.choice(ALNUM_CHARS) for _ in range(length))


class PasswordChecker(PasswordHasher):
    """
    Checks password using multiple hashers.

    The first hasher is considered default and used to hash passwords.
    All the rest are used to check the passed password.
    """

    @property
    def requires_update(self) -> bool:
        if self._requires_update is None:
            raise ValueError(
                "Run password check before accessing " "'requires_update' property."
            )
        return self._requires_update

    def __init__(self, hashers: Sequence[PasswordHasher]):
        assert len(hashers) > 0
        self._hashers = hashers
        self._requires_update: Optional[bool] = None

    async def check(self, password: str, encoded: str) -> bool:
        self._requires_update = False
        algorithm, _ = encoded.split("$", 1)

        for hasher in self._hashers:
            if hasher.algorithm == algorithm:
                return await hasher.check(password, encoded)

            # the default hasher is the one at index 0
            # when it's algorithm is not the one used to hash the password
            # then the password must be updated
            self._requires_update = True
        return False

    async def make(self, password: str, salt: str = None, **kwargs: Any) -> str:
        return await self._hashers[0].make(password, salt, **kwargs)


class BCryptPasswordHasher(PasswordHasher):
    algorithm: str = "bcrypt_sha256"
    rounds: int = 12
    digest: Callable = hashlib.sha256

    def __init__(self) -> None:
        assert bcrypt, "bcrypt library is not installed."

    async def check(self, password: str, encoded: str) -> bool:
        algorithm, data = encoded.split("$", 1)
        assert algorithm == self.algorithm
        reference = await self.make(password, data)
        return hmac.compare_digest(encoded.encode(), reference.encode())

    async def make(
        self, password: str, salt: str = None, *args: Any, **kwargs: Any
    ) -> str:
        salt = salt or self.generate_salt()

        if self.digest is not None:
            password = binascii.hexlify(
                self.digest(password.encode()).digest()
            ).decode()

        hash_ = await run_in_threadpool(bcrypt.hashpw, password.encode(), salt.encode())
        return "%s$%s" % (self.algorithm, hash_.decode())

    def generate_salt(self, length: int = 8) -> str:
        return bcrypt.gensalt(self.rounds).decode()


class Argon2PasswordHasher(PasswordHasher):
    algorithm: str = "argon2"
    time_cost: int = 2
    memory_cost: int = 512
    parallelism: int = 2

    def __init__(self) -> None:
        assert argon2, "argon2 library is not installed."

    async def check(self, password: str, encoded: str) -> bool:
        algorithm, data = encoded.split("$", 1)
        assert algorithm == self.algorithm

        try:
            return argon2.low_level.verify_secret(
                ("$" + data).encode(), password.encode(), type=argon2.low_level.Type.I
            )
        except argon2.exceptions.VerificationError:
            return False

    async def make(self, password: str, salt: str = None, **kwargs: Any) -> str:
        salt = salt or self.generate_salt()
        data = argon2.low_level.hash_secret(
            password.encode(),
            salt.encode(),
            time_cost=self.time_cost,
            memory_cost=self.memory_cost,
            parallelism=self.parallelism,
            hash_len=argon2.DEFAULT_HASH_LENGTH,
            type=argon2.low_level.Type.I,
        ).decode()
        return self.algorithm + data


class PBKDF2PasswordHasher(PasswordHasher):
    """
    PBKDF2 password hashing algorithm.

    The result is a 64 byte binary string.
    """

    algorithm: str = "pbkdf2_sha256"
    rounds: int = 150000
    digest: Callable = hashlib.sha256

    async def check(self, password: str, encoded: str) -> bool:
        algorithm, rounds, salt, hash_ = encoded.split("$", 3)
        assert algorithm == self.algorithm
        reference = await self.make(password, salt, rounds=int(rounds))
        return hmac.compare_digest(encoded.encode(), reference.encode())

    async def make(
        self, password: str, salt: str = None, rounds: int = None, **kwargs: Any
    ) -> str:
        rounds = rounds or self.rounds
        salt = salt or self.generate_salt()
        hash_ = await run_in_threadpool(
            hashlib.pbkdf2_hmac,
            self.digest().name,
            password.encode(),
            salt.encode(),
            int(rounds),
            **kwargs,
        )
        hash_ = base64.b64encode(hash_).decode().strip()
        return "%s$%d$%s$%s" % (self.algorithm, self.rounds, salt, hash_)


class InsecurePasswordHasher(PasswordHasher):
    algorithm: str = "plain"

    async def check(self, password: str, encoded: str) -> bool:
        algorithm, data = encoded.split("$", 1)
        assert algorithm == self.algorithm
        return password == data

    async def make(self, password: str, *args: Any, **kwargs: Any) -> str:
        return "%s$%s" % (self.algorithm, password)

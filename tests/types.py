import sys
from typing import Protocol

from starlette.types import AppType

if sys.version_info >= (3, 10):  # pragma: no cover
    from typing import ParamSpec
else:  # pragma: no cover
    from typing_extensions import ParamSpec

from starlette.testclient import TestClient

P = ParamSpec("P")


class TestClientFactory(Protocol):
    __test__ = False  # type: ignore

    def __call__(
        self,
        app: AppType,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> TestClient:
        ...

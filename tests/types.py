import sys
from typing import Protocol

if sys.version_info >= (3, 10):  # pragma: no cover
    from typing import ParamSpec
else:  # pragma: no cover
    from typing_extensions import ParamSpec

from starlette.testclient import TestClient

P = ParamSpec("P")


class ClientFactoryProtocol(Protocol):  # pragma: no cover
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> TestClient:
        ...

from typing import Dict, Optional, Protocol, Union

from httpx import Cookies, Headers

from starlette.testclient import TestClient
from starlette.types import ASGIApp


class TestClientFactory(Protocol):  # pragma: no cover
    __test__ = False  # type: ignore

    def __call__(
        self,
        app: ASGIApp,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
        root_path: str = "",
        cookies: Optional[Union[Cookies, Dict[str, str]]] = None,
        headers: Optional[Headers] = None,
        follow_redirects: bool = True,
    ) -> TestClient:
        ...

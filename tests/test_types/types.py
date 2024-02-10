from typing import Any, Awaitable, Callable, Dict, Iterable

from starlette.responses import Response
from starlette.testclient import TestClient

TestClientFactory = Callable[..., TestClient]

WSGIResponse = Iterable[bytes]
StartResponse = Callable[..., Any]
Environment = Dict[str, Any]

AsyncEndpoint = Callable[..., Awaitable[Response]]
SyncEndpoint = Callable[..., Response]

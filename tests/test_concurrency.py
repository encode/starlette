from contextvars import ContextVar

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


def test_accessing_context_from_threaded_sync_endpoint(test_client_factory) -> None:
    ctxvar: ContextVar[bytes] = ContextVar("ctxvar")
    ctxvar.set(b"data")

    def endpoint(request: Request) -> Response:
        return Response(ctxvar.get())

    app = Starlette(routes=[Route("/", endpoint)])
    client = test_client_factory(app)

    resp = client.get("/")
    assert resp.content == b"data"

from __future__ import annotations

import itertools
import sys
from asyncio import Task, current_task as asyncio_current_task
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import anyio
import anyio.lowlevel
import pytest
import sniffio
import trio.lowlevel

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.testclient import ASGIInstance, AsyncTestClient
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketDisconnect
from tests.types import AsyncTestClientFactory

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup


def mock_service_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"mock": "example"})


mock_service = Starlette(routes=[Route("/", endpoint=mock_service_endpoint)])


def current_task() -> Task[Any] | trio.lowlevel.Task:
    # anyio's TaskInfo comparisons are invalid after their associated native
    # task object is GC'd https://github.com/agronholm/anyio/issues/324
    asynclib_name = sniffio.current_async_library()
    if asynclib_name == "trio":
        return trio.lowlevel.current_task()

    if asynclib_name == "asyncio":
        task = asyncio_current_task()
        if task is None:
            raise RuntimeError("must be called from a running task")  # pragma: no cover
        return task
    raise RuntimeError(f"unsupported asynclib={asynclib_name}")  # pragma: no cover


def startup() -> None:
    raise RuntimeError()


@pytest.mark.anyio
async def test_use_testclient_in_endpoint(async_test_client_factory: AsyncTestClientFactory) -> None:
    """
    We should be able to use the test client within applications.

    This is useful if we need to mock out other services,
    during tests or in development.
    """

    async def homepage(request: Request) -> JSONResponse:
        client = async_test_client_factory(mock_service)
        response = await client.get("/")
        return JSONResponse(response.json())

    app = Starlette(routes=[Route("/", endpoint=homepage)])

    client = async_test_client_factory(app)
    response = await client.get("/")
    assert response.json() == {"mock": "example"}


def test_testclient_headers_behavior() -> None:
    """
    We should be able to use the test client with user defined headers.

    This is useful if we need to set custom headers for authentication
    during tests or in development.
    """

    client = AsyncTestClient(mock_service)
    assert client.headers.get("user-agent") == "testclient"

    client = AsyncTestClient(mock_service, headers={"user-agent": "non-default-agent"})
    assert client.headers.get("user-agent") == "non-default-agent"

    client = AsyncTestClient(mock_service, headers={"Authentication": "Bearer 123"})
    assert client.headers.get("user-agent") == "testclient"
    assert client.headers.get("Authentication") == "Bearer 123"


async def test_use_testclient_as_contextmanager(
    async_test_client_factory: AsyncTestClientFactory, anyio_backend_name: str
) -> None:
    """
    This test asserts a number of properties that are important for an
    app level task_group
    """
    counter = itertools.count()
    identity_runvar = anyio.lowlevel.RunVar[int]("identity_runvar")

    def get_identity() -> int:
        try:
            return identity_runvar.get()
        except LookupError:
            token = next(counter)
            identity_runvar.set(token)
            return token

    startup_task = object()
    startup_loop = None
    shutdown_task = object()
    shutdown_loop = None

    @asynccontextmanager
    async def lifespan_context(app: Starlette) -> AsyncGenerator[None, None]:
        nonlocal startup_task, startup_loop, shutdown_task, shutdown_loop

        startup_task = current_task()
        startup_loop = get_identity()
        async with anyio.create_task_group():
            yield
        shutdown_task = current_task()
        shutdown_loop = get_identity()

    async def loop_id(request: Request) -> JSONResponse:
        return JSONResponse(get_identity())

    app = Starlette(
        lifespan=lifespan_context,
        routes=[Route("/loop_id", endpoint=loop_id)],
    )

    client = async_test_client_factory(app)

    async with client:
        # within a TestClient context every async request runs in the same thread
        assert (await client.get("/loop_id")).json() == 0
        assert (await client.get("/loop_id")).json() == 0

    # that thread is also the same as the lifespan thread
    assert startup_loop == 0
    assert shutdown_loop == 0

    # lifespan events run in the same task, this is important because a task
    # group must be entered and exited in the same task.
    assert startup_task is shutdown_task

    # outside the TestClient context, new requests continue to spawn in new
    # event loops in new threads
    assert (await client.get("/loop_id")).json() == 0
    assert (await client.get("/loop_id")).json() == 0

    first_task = startup_task

    async with client:
        # the TestClient context can be re-used, starting a new lifespan task
        # in a new thread
        assert (await client.get("/loop_id")).json() == 0
        assert (await client.get("/loop_id")).json() == 0

    assert startup_loop == 0
    assert shutdown_loop == 0

    # lifespan events still run in the same task, with the context but...
    assert startup_task is shutdown_task

    # ... the second TestClient context creates a new lifespan task.
    assert first_task is not startup_task


@pytest.mark.anyio
async def test_error_on_startup(async_test_client_factory: AsyncTestClientFactory) -> None:
    with pytest.deprecated_call(match="The on_startup and on_shutdown parameters are deprecated"):
        startup_error_app = Starlette(on_startup=[startup])

    with pytest.raises(ExceptionGroup) as excinfo:
        async with async_test_client_factory(startup_error_app):
            pass  # pragma: no cover

    assert excinfo.group_contains(RuntimeError)


@pytest.mark.anyio
async def test_exception_in_middleware(async_test_client_factory: AsyncTestClientFactory) -> None:
    class MiddlewareException(Exception):
        pass

    class BrokenMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            raise MiddlewareException()

    broken_middleware = Starlette(middleware=[Middleware(BrokenMiddleware)])

    with pytest.raises(ExceptionGroup) as excinfo:
        async with async_test_client_factory(broken_middleware):
            pass  # pragma: no cover

    assert excinfo.group_contains(MiddlewareException)


@pytest.mark.anyio
async def test_testclient_asgi2(async_test_client_factory: AsyncTestClientFactory) -> None:
    def app(scope: Scope) -> ASGIInstance:
        async def inner(receive: Receive, send: Send) -> None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"text/plain"]],
                }
            )
            await send({"type": "http.response.body", "body": b"Hello, world!"})

        return inner

    client = async_test_client_factory(app)  # type: ignore
    response = await client.get("/")
    assert response.text == "Hello, world!"


@pytest.mark.anyio
async def test_testclient_asgi3(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"Hello, world!"})

    client = async_test_client_factory(app)
    response = await client.get("/")
    assert response.text == "Hello, world!"


@pytest.mark.anyio
async def test_websocket_blocking_receive(async_test_client_factory: AsyncTestClientFactory) -> None:
    def app(scope: Scope) -> ASGIInstance:
        async def respond(websocket: WebSocket) -> None:
            await websocket.send_json({"message": "test"})

        async def asgi(receive: Receive, send: Send) -> None:
            websocket = WebSocket(scope, receive=receive, send=send)
            await websocket.accept()
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(respond, websocket)
                try:
                    # this will block as the client does not send us data
                    # it should not prevent `respond` from executing though
                    await websocket.receive_json()
                except WebSocketDisconnect:
                    pass

        return asgi

    client = async_test_client_factory(app)  # type: ignore
    async with await client.websocket_connect("/") as websocket:
        data = await websocket.receive_json()
        assert data == {"message": "test"}


@pytest.mark.anyio
async def test_websocket_not_block_on_close(async_test_client_factory: AsyncTestClientFactory) -> None:
    cancelled = False

    def app(scope: Scope) -> ASGIInstance:
        async def asgi(receive: Receive, send: Send) -> None:
            nonlocal cancelled
            try:
                websocket = WebSocket(scope, receive=receive, send=send)
                await websocket.accept()
                await anyio.sleep_forever()
            except anyio.get_cancelled_exc_class():
                cancelled = True
                raise

        return asgi

    client = async_test_client_factory(app)  # type: ignore
    async with await client.websocket_connect("/"):
        ...
    assert cancelled


@pytest.mark.anyio
async def test_client(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        client = scope.get("client")
        assert client is not None
        host, port = client
        response = JSONResponse({"host": host, "port": port})
        await response(scope, receive, send)

    client = async_test_client_factory(app)
    response = await client.get("/")
    assert response.json() == {"host": "testclient", "port": 50000}


@pytest.mark.anyio
async def test_client_custom_client(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        client = scope.get("client")
        assert client is not None
        host, port = client
        response = JSONResponse({"host": host, "port": port})
        await response(scope, receive, send)

    client = async_test_client_factory(app, client=("192.168.0.1", 3000))
    response = await client.get("/")
    assert response.json() == {"host": "192.168.0.1", "port": 3000}


@pytest.mark.anyio
@pytest.mark.parametrize("param", ("2020-07-14T00:00:00+00:00", "España", "voilà"))
async def test_query_params(async_test_client_factory: AsyncTestClientFactory, param: str) -> None:
    def homepage(request: Request) -> Response:
        return Response(request.query_params["param"])

    app = Starlette(routes=[Route("/", endpoint=homepage)])
    client = async_test_client_factory(app)
    response = await client.get("/", params={"param": param})
    assert response.text == param


@pytest.mark.anyio
@pytest.mark.parametrize(
    "domain, ok",
    [
        pytest.param(
            "testserver",
            True,
            marks=[
                pytest.mark.xfail(
                    sys.version_info < (3, 11),
                    reason="Fails due to domain handling in http.cookiejar module (see #2152)",
                ),
            ],
        ),
        ("testserver.local", True),
        ("localhost", False),
        ("example.com", False),
    ],
)
async def test_domain_restricted_cookies(
    async_test_client_factory: AsyncTestClientFactory, domain: str, ok: bool
) -> None:
    """
    Test that test client discards domain restricted cookies which do not match the
    base_url of the testclient (`http://testserver` by default).

    The domain `testserver.local` works because the Python http.cookiejar module derives
    the "effective domain" by appending `.local` to non-dotted request domains
    in accordance with RFC 2965.
    """

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = Response("Hello, world!", media_type="text/plain")
        response.set_cookie(
            "mycookie",
            "myvalue",
            path="/",
            domain=domain,
        )
        await response(scope, receive, send)

    client = async_test_client_factory(app)
    response = await client.get("/")
    cookie_set = len(response.cookies) == 1
    assert cookie_set == ok


@pytest.mark.anyio
async def test_forward_follow_redirects(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if "/ok" in scope["path"]:
            response = Response("ok")
        else:
            response = RedirectResponse("/ok")
        await response(scope, receive, send)

    client = async_test_client_factory(app, follow_redirects=True)
    response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_forward_nofollow_redirects(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = RedirectResponse("/ok")
        await response(scope, receive, send)

    client = async_test_client_factory(app, follow_redirects=False)
    response = await client.get("/")
    assert response.status_code == 307


@pytest.mark.anyio
async def test_with_duplicate_headers(async_test_client_factory: AsyncTestClientFactory) -> None:
    def homepage(request: Request) -> JSONResponse:
        return JSONResponse({"x-token": request.headers.getlist("x-token")})

    app = Starlette(routes=[Route("/", endpoint=homepage)])
    client = async_test_client_factory(app)
    response = await client.get("/", headers=[("x-token", "foo"), ("x-token", "bar")])
    assert response.json() == {"x-token": ["foo", "bar"]}


@pytest.mark.anyio
async def test_merge_url(async_test_client_factory: AsyncTestClientFactory) -> None:
    def homepage(request: Request) -> Response:
        return Response(request.url.path)

    app = Starlette(routes=[Route("/api/v1/bar", endpoint=homepage)])
    client = async_test_client_factory(app, base_url="http://testserver/api/v1/")
    response = await client.get("/bar")
    assert response.text == "/api/v1/bar"


@pytest.mark.anyio
async def test_raw_path_with_querystring(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = Response(scope.get("raw_path"))
        await response(scope, receive, send)

    client = async_test_client_factory(app)
    response = await client.get("/hello-world", params={"foo": "bar"})
    assert response.content == b"/hello-world"


@pytest.mark.anyio
async def test_websocket_raw_path_without_params(async_test_client_factory: AsyncTestClientFactory) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        websocket = WebSocket(scope, receive=receive, send=send)
        await websocket.accept()
        raw_path = scope.get("raw_path")
        assert raw_path is not None
        await websocket.send_bytes(raw_path)

    client = async_test_client_factory(app)
    async with await client.websocket_connect("/hello-world", params={"foo": "bar"}) as websocket:
        data = await websocket.receive_bytes()
        assert data == b"/hello-world"


@pytest.mark.anyio
async def test_timeout_deprecation() -> None:
    with pytest.deprecated_call(match="You should not use the 'timeout' argument with the TestClient."):
        client = AsyncTestClient(mock_service)
        await client.get("/", timeout=1)

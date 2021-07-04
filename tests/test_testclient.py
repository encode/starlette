import asyncio
import itertools
import sys

import anyio
import pytest
import sniffio
import trio.lowlevel

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.testclient import CancelledError, ClosedError
from starlette.websockets import WebSocket, WebSocketDisconnect

if sys.version_info >= (3, 7):  # pragma: no cover
    from asyncio import current_task as asyncio_current_task
    from contextlib import asynccontextmanager
else:  # pragma: no cover
    asyncio_current_task = asyncio.Task.current_task
    from contextlib2 import asynccontextmanager

mock_service = Starlette()


@mock_service.route("/")
def mock_service_endpoint(request):
    return JSONResponse({"mock": "example"})


def current_task():
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


startup_error_app = Starlette()


@startup_error_app.on_event("startup")
def startup():
    raise RuntimeError()


def test_use_testclient_in_endpoint(test_client_factory):
    """
    We should be able to use the test client within applications.

    This is useful if we need to mock out other services,
    during tests or in development.
    """

    app = Starlette()

    @app.route("/")
    def homepage(request):
        client = test_client_factory(mock_service)
        response = client.get("/")
        return JSONResponse(response.json())

    client = test_client_factory(app)
    response = client.get("/")
    assert response.json() == {"mock": "example"}


def test_use_testclient_as_contextmanager(test_client_factory, anyio_backend_name):
    """
    This test asserts a number of properties that are important for an
    app level task_group
    """
    counter = itertools.count()
    identity_runvar = anyio.lowlevel.RunVar[int]("identity_runvar")

    def get_identity():
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
    async def lifespan_context(app):
        nonlocal startup_task, startup_loop, shutdown_task, shutdown_loop

        startup_task = current_task()
        startup_loop = get_identity()
        async with anyio.create_task_group() as app.task_group:
            yield
        shutdown_task = current_task()
        shutdown_loop = get_identity()

    app = Starlette(lifespan=lifespan_context)

    @app.route("/loop_id")
    async def loop_id(request):
        return JSONResponse(get_identity())

    client = test_client_factory(app)

    with client:
        # within a TestClient context every async request runs in the same thread
        assert client.get("/loop_id").json() == 0
        assert client.get("/loop_id").json() == 0

    # that thread is also the same as the lifespan thread
    assert startup_loop == 0
    assert shutdown_loop == 0

    # lifespan events run in the same task, this is important because a task
    # group must be entered and exited in the same task.
    assert startup_task is shutdown_task

    # outside the TestClient context, new requests continue to spawn in new
    # eventloops in new threads
    assert client.get("/loop_id").json() == 1
    assert client.get("/loop_id").json() == 2

    first_task = startup_task

    with client:
        # the TestClient context can be re-used, starting a new lifespan task
        # in a new thread
        assert client.get("/loop_id").json() == 3
        assert client.get("/loop_id").json() == 3

    assert startup_loop == 3
    assert shutdown_loop == 3

    # lifespan events still run in the same task, with the context but...
    assert startup_task is shutdown_task

    # ... the second TestClient context creates a new lifespan task.
    assert first_task is not startup_task


class ExceptionGroup(anyio.ExceptionGroup):
    def __init__(self, exceptions):  # pragma: no cover
        super().__init__()
        self.exceptions = exceptions


def test_testclient_cancel_propagate_lifespan_failure(test_client_factory):
    lifespan_taskgroup = None
    event = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal lifespan_taskgroup, event
        event = anyio.Event()
        async with anyio.create_task_group() as lifespan_taskgroup:
            yield

    app = Starlette(lifespan=lifespan)

    @app.route("/throw")
    async def throw(self):
        async def throw():
            await event.wait()
            raise MyError

        lifespan_taskgroup.start_soon(throw)
        return JSONResponse("good")

    @app.route("/ping")
    async def ping(self):
        return JSONResponse("pong")

    @app.route("/sleep_forever")
    async def sleep_forever(self):
        event.set()
        await anyio.sleep_forever()

    class MyError(Exception):
        pass

    client = test_client_factory(app)

    client.get("/ping").json() == "pong"  # app works outside of lifespan

    for _ in range(2):  # context manager can be re-used
        try:
            client.__enter__()
            assert client.get("/ping").json() == "pong"
            assert client.get("/throw").json() == "good"
            with pytest.raises(CancelledError):
                client.get("/sleep_forever")
            with pytest.raises(ClosedError):
                client.get("/sleep_forever")
        except BaseException as e:  # pragma: no cover
            try:
                client.__exit__(*sys.exc_info())
            except BaseException as f:
                raise ExceptionGroup((e, f)) from None
            raise
        with pytest.raises(MyError):
            client.__exit__(None, None, None)

    # app is no-longer shutdown outside of lifespan
    client.get("/ping").json() == "pong"


def test_error_on_startup(test_client_factory):
    with pytest.raises(RuntimeError):
        with test_client_factory(startup_error_app):
            pass  # pragma: no cover


def test_exception_in_middleware(test_client_factory):
    class MiddlewareException(Exception):
        pass

    class BrokenMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            raise MiddlewareException()

    broken_middleware = Starlette(middleware=[Middleware(BrokenMiddleware)])

    with pytest.raises(MiddlewareException):
        with test_client_factory(broken_middleware):
            pass  # pragma: no cover


def test_testclient_asgi2(test_client_factory):
    def app(scope):
        async def inner(receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"text/plain"]],
                }
            )
            await send({"type": "http.response.body", "body": b"Hello, world!"})

        return inner

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "Hello, world!"


def test_testclient_asgi3(test_client_factory):
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"Hello, world!"})

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "Hello, world!"


def test_websocket_blocking_receive(test_client_factory):
    def app(scope):
        async def respond(websocket):
            await websocket.send_json({"message": "test"})

        async def asgi(receive, send):
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

    client = test_client_factory(app)
    with client.websocket_connect("/") as websocket:
        data = websocket.receive_json()
        assert data == {"message": "test"}

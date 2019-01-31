import os
from functools import partial

import pytest

from starlette.applications import Starlette
from starlette.middleware.lifespan import LifespanMiddleware
from starlette.routing import MountedAppLifespanHandler
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient


class App:
    raise_on_startup = False
    raise_on_shutdown = False

    def __init__(self, scope):
        pass

    async def __call__(self, receive, send):
        message = await receive()
        assert message["type"] == "lifespan.startup"
        if self.raise_on_startup:
            raise RuntimeError()
        await send({"type": "lifespan.startup.complete"})

        message = await receive()
        assert message["type"]
        if self.raise_on_shutdown:
            raise RuntimeError()
        await send({"type": "lifespan.shutdown.complete"})


class RaiseOnStartup(App):
    raise_on_startup = True


class RaiseOnShutdown(App):
    raise_on_shutdown = True


def test_lifespan_handler():
    startup_complete = False
    cleanup_complete = False
    handler = LifespanMiddleware(App)

    @handler.on_event("startup")
    def run_startup():
        nonlocal startup_complete
        startup_complete = True

    @handler.on_event("shutdown")
    def run_cleanup():
        nonlocal cleanup_complete
        cleanup_complete = True

    assert not startup_complete
    assert not cleanup_complete
    with TestClient(handler):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete


def test_async_lifespan_handler():
    startup_complete = False
    cleanup_complete = False
    handler = LifespanMiddleware(App)

    @handler.on_event("startup")
    async def run_startup():
        nonlocal startup_complete
        startup_complete = True

    @handler.on_event("shutdown")
    async def run_cleanup():
        nonlocal cleanup_complete
        cleanup_complete = True

    assert not startup_complete
    assert not cleanup_complete
    with TestClient(handler):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete


def test_raise_on_startup():
    handler = LifespanMiddleware(RaiseOnStartup)

    with pytest.raises(RuntimeError):
        with TestClient(handler):
            pass  # pragma: nocover


def test_raise_on_shutdown():
    handler = LifespanMiddleware(RaiseOnShutdown)

    with pytest.raises(RuntimeError):
        with TestClient(handler):
            pass


def test_app_lifespan():
    startup_complete = False
    cleanup_complete = False
    app = Starlette()

    @app.on_event("startup")
    def run_startup():
        nonlocal startup_complete
        startup_complete = True

    @app.on_event("shutdown")
    def run_cleanup():
        nonlocal cleanup_complete
        cleanup_complete = True

    assert not startup_complete
    assert not cleanup_complete
    with TestClient(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete


def test_mounted_app_lifespan_handler():

    # apps[0] as the root app
    apps = [Starlette() for _ in range(0, 10)]
    startup_complete = [False] * len(apps)
    shutdown_complete = [False] * len(apps)

    def run_startup(idx):
        nonlocal startup_complete
        startup_complete[idx] = True

    def run_shutdown(idx):
        nonlocal shutdown_complete
        shutdown_complete[idx] = True

    [
        app.add_event_handler("startup", partial(run_startup, idx))
        for idx, app in enumerate(apps)
    ]
    [
        app.add_event_handler("shutdown", partial(run_shutdown, idx))
        for idx, app in enumerate(apps)
    ]

    assert not any(startup_complete)
    assert not any(shutdown_complete)

    [apps[0].mount(f"/{idx}", app) for idx, app in enumerate(apps[1:])]

    handler = partial(MountedAppLifespanHandler, apps[0])

    with TestClient(handler):
        assert all(startup_complete[1:])
        assert not any(shutdown_complete[1:])
    assert all(startup_complete[1:])
    assert all(shutdown_complete[1:])


def test_mounted_app_lifespan_handler_with_error(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    app = Starlette()
    app.mount("/static", StaticFiles(directory=tmpdir))
    app.mount("/fail_startup", RaiseOnStartup)
    app.mount("/fail_shutdown", RaiseOnShutdown)

    for asgi_app in (app, App):
        handler = partial(MountedAppLifespanHandler, asgi_app)

        with TestClient(handler):
            pass

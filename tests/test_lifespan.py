from starlette.applications import Starlette
from starlette.lifespan import LifespanContext, LifespanMiddleware


class App:
    def __init__(self, scope):
        pass

    async def __call__(self, receive, send):
        message = await receive()
        assert message["type"] == "lifespan.startup"
        await send({'type': 'lifespan.startup.complete'})

        message = await receive()
        assert message['type']
        await send({'type': 'lifespan.shutdown.complete'})


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
    with LifespanContext(handler):
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
    with LifespanContext(handler):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete


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
    with LifespanContext(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete

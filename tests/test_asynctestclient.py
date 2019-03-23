import pytest

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import AsyncTestClient

mock_service = Starlette()


@mock_service.route("/")
def mock_service_endpoint(request):
    return JSONResponse({"mock": "example"})


app = Starlette()


@pytest.mark.asyncio
@app.route("/")
async def homepage(request):
    client = AsyncTestClient(mock_service)
    response = await client.get("/")
    return JSONResponse(response.json())


startup_error_app = Starlette()


@startup_error_app.on_event("startup")
def startup():
    raise RuntimeError()


@pytest.mark.asyncio
async def test_use_asynctestclient_in_endpoint():
    """
    We should be able to use the test client within applications.

    This is useful if we need to mock out other services,
    during tests or in development.
    """
    client = AsyncTestClient(app)
    response = await client.get("/")
    assert response.json() == {"mock": "example"}


@pytest.mark.asyncio
async def test_asynctestclient_as_contextmanager():
    async with AsyncTestClient(app):
        pass


@pytest.mark.asyncio
async def test_error_on_startup():
    with pytest.raises(RuntimeError):
        async with AsyncTestClient(startup_error_app):
            pass  # pragma: no cover


# TODO test_asynctestclient_asgi2
# `requests_async` is ASGI 3 only as of now


@pytest.mark.asyncio
async def test_asynctestclient_asgi3():
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"Hello, world!"})

    client = AsyncTestClient(app)
    response = await client.get("/")
    assert response.text == "Hello, world!"

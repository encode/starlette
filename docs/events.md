
Starlette applications can run a lifespan context manager for dealing with
code that needs to run before the application starts up, or when the application
is shutting down.

Starlette will not start serving any incoming requests until the lifespan has been run.

```python
import contextlib
import anyio
from starlette.applications import Starlette


@contextlib.asynccontextmanager
async def lifespan(app):
    async with some_async_resource():
        yield


routes = [
    ...
]

app = Starlette(routes=routes, lifespan=lifespan)
```

Consider using [`anyio.create_task_group()`](https://anyio.readthedocs.io/en/stable/tasks.html)
for managing asynchronous tasks.

## Lifespan State

The lifespan can also accept a `state` argument, which is a dictionary
that can be used to share the objects between the startup and shutdown handlers,
and the requests.

```python
import contextlib
import httpx
from starlette.applications import Starlette
from starlette.routing import Route


@contextlib.asynccontextmanager
async def lifespan(app, state):
    async with httpx.AsyncClient() as client:
        state["http_client"] = client
        yield


app = Starlette(
    lifespan=lifespan,
    routes=[Route("/", homepage)]
)
```

The `state` received on the requests is a **shallow** copy of the state received on the
lifespan event.

## Running lifespans

You can use `TestClient` as a context manager, to ensure that the lifespan is called.

```python
from example import app
from starlette.testclient import TestClient


def test_homepage():
    with TestClient(app) as client:
        # Application's lifespan is called on entering the block.
        response = client.get("/")
        assert response.status_code == 200

    # And the lifespan's teardown is run when exiting the block.
```

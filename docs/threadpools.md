Starlette supports both `async` and `sync` routes and background tasks.
The sync part is running inside a threadpool by using [`AnyIO`](https://github.com/agronholm/anyio).

The `AnyIO` library by default starts a threadpool with a fixed number of threads, which works for most cases.
But since the threadpool is shared by both routes and background tasks,
it might be useful to control the number of threads.


```py
import anyio
from starlette.applications import Starlette
from starlette.background import BackgroundTasks
from starlette.request import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# Set number of threads in threadpool to 100
anyio.to_thread.current_default_thread_limiter().total_tokens = 100


def do_task():
    ...


def endpoint(request: Request) -> JSONResponse:
    tasks = BackgroundTasks()
    tasks.add_task(do_task)
    return JSONResponse({"status": "Success"}, background=tasks)


app = Starlette(routes=[Route("/", endpoint=endpoint)])
```

For more information checkout AnyIO [docs](https://anyio.readthedocs.io/en/stable/threads.html#adjusting-the-default-maximum-worker-thread-count)

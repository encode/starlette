
Starlette includes a `BackgroundTask` class to allow for long running tasks to be done in the background.

### Background Task

Signature: `BackgroundTask(func, *args, **kwargs)

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.tasks import BackgroundTask

app = Starlette()

@app.route('/start_task/{arg}')
def init_task(request, arg):
    task = BackgroundTask(some_long_task, arg)
    return JSONResponse(
        'Task was initiated',
        202,
        background=task
    )

def some_long_task(arg):
    pass
```
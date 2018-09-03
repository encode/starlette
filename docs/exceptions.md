
Starlette includes an exception handling middleware that you can use in order
to dispatch different classes of exceptions to different handlers.

To see how this works, we'll start by with this small ASGI application:

```python
from starlette.exceptions import ExceptionMiddleware, HTTPException


class App:
    def __init__(self, scope):
        raise HTTPException(403)


app = ExceptionMiddleware(App)
```

If you run the app and make an HTTP request to it, you'll get a plain text
response with a "403 Permission Denied" response. This is the behaviour that the
default handler responds with when an `HTTPException` class or subclass is raised.

Let's change the exception handling, so that we get JSON error responses
instead:


```python
from starlette.exceptions import ExceptionMiddleware, HTTPException
from starlette.response import JSONResponse


class App:
    def __init__(self, scope):
        raise HTTPException(403)


def handler(request, exc):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


app = ExceptionMiddleware(App)
app.add_exception_handler(HTTPException, handler)
```

Now if we make a request to the application, we'll get back a JSON encoded
HTTP response.

## ExceptionMiddleware

The exception middleware catches and handles the exceptions, returning
appropriate HTTP responses.

* `ExceptionMiddleware(app)` - Instantiate the exception handler, wrapping up
it around an inner ASGI application.

Adding handlers:

* `.add_exception_handler(exc_class, handler)` - Set a handler function to run
for the given exception class.

## HTTPException

The `HTTPException` class provides a base class that you can use for any
standard HTTP error conditions. The `ExceptionMiddleware` implementation
defaults to returning plain-text HTTP responses for any `HTTPException`.

* `HTTPException(status_code, detail=None)`

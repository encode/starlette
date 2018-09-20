
Starlette includes the classes `HTTPEndpoint` and `WebSocketEndpoint` that provide a class-based view pattern which
handles HTTP method dispatching and WebSocket sessions.

### HTTPEndpoint

The `HTTPEndpoint` class can be used as an ASGI application:

```python
from starlette.responses import PlainTextResponse
from starlette.endpoints import HTTPEndpoint


class App(HTTPEndpoint):
    async def get(self, request):
        return PlainTextResponse(f"Hello, world!")
```

If you're using a Starlette application instance to handle routing, you can
dispatch to an `HTTPEndpoint` class by using the `@app.route()` decorator, or the
`app.add_route()` function. Make sure to dispatch to the class itself, rather
than to an instance of the class:

```python
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.endpoints import HTTPEndpoint


app = Starlette()


@app.route("/")
class Homepage(HTTPEndpoint):
    async def get(self, request):
        return PlainTextResponse(f"Hello, world!")


@app.route("/{username}")
class User(HTTPEndpoint):
    async def get(self, request, username):
        return PlainTextResponse(f"Hello, {username}")
```

HTTP endpoint classes will respond with "405 Method not allowed" responses for any
request methods which do not map to a corresponding handler.

### WebSocketEndpoint

The `WebSocketEndpoint` class is an ASGI application that presents a wrapper around
the functionality of a `WebSocket` instance. 

The ASGI connection details are accessible on the endpoint instance:

* `.scope` - The request scope.
* `.websocket` - The `WebSocket` instance.
* `.close_code` - The close code used when the websocket session is closed.
* `.kwargs` - The `scope` kwargs.

There are three overridable methods for handling specific ASGI websocket message types:

* `async def on_connect(self)`
* `async def on_receive(self, bytes=None, text=None)`
* `async def on_disconnect(self)`

```python
from starlette.endpoints import WebSocketEndpoint


class App(WebSocketEndpoint):

    async def on_connect(self):
        """
        Override the default `on_connect` behaviour and manually handle websocket acceptance.

        For example, it is possible to retrieve the subprotocols available on the websocket instance
        and negotiate its accept behaviour.

            async def on_connect(self):
                subprotocols = self.websocket['subprotocols']
                ...
                await self.websocket.accept(subprotocol=subprotocol)
        """
        await self.websocket.accept()

    async def on_receive(self, **kwargs):
        """Override `on_receive` to handle the message bytes or text sent over the websocket."""
        _bytes = kwargs.get("bytes")
        if _bytes is not None:
            await self.websocket.send_text(b"Message: " + _bytes)
        _text = kwargs.get("text")
        if _text is not None:
            await self.websocket.send_text(f"Message: {_text}")

    async def on_disconnect(self):
        """Override this method to perform any cleanup tasks after the websocket is closed."""
```

The `WebSocketEndpoint` can also be used with the `Starlette` application class:

```python
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.endpoints import HTTPEndpoint, WebSocketEndpoint


app = Starlette()


@app.route("/")
class Homepage(HTTPEndpoint):
    async def get(self, request):
        return PlainTextResponse(f"Hello, world!")


@app.route("/ws")
class WebSocketHandler(WebSocketEndpoint):
    pass
```

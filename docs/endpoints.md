
Starlette includes the classes `HTTPEndpoint` and `WebSocketEndpoint` that provide a class-based view pattern for
handling HTTP method dispatching and WebSocket sessions.

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

The ASGI connection scope is accessible on the endpoint instance via `.scope`.

There are three overridable methods for handling specific ASGI websocket message types:

* `async def on_connect(self, **kwargs)`
* `async def on_receive(self, **kwargs)`
* `async def on_disconnect(self, close_code)`

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
import uvicorn
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint, HTTPEndpoint
from starlette.responses import HTMLResponse

app = Starlette()

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


@app.route("/")
class HTTPApp(HTTPEndpoint):
    async def get(self, request):
        return HTMLResponse(html)


@app.websocket_route("/ws")
class WebSocketEchoEndpoint(WebSocketEndpoint):
    async def on_receive(self, websocket, **kwargs):
        await websocket.send_text(f"Message text was: {kwargs['text']}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

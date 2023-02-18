
Starlette includes a `WebSocket` class that fulfils a similar role
to the HTTP request, but that allows sending and receiving data on a websocket.

### WebSocket

Signature: `WebSocket(scope, receive=None, send=None)`

```python
from starlette.websockets import WebSocket


async def app(scope, receive, send):
    websocket = WebSocket(scope=scope, receive=receive, send=send)
    await websocket.accept()
    await websocket.send_text('Hello, world!')
    await websocket.close()
```

WebSockets present a mapping interface, so you can use them in the same
way as a `scope`.

For instance: `websocket['path']` will return the ASGI path.

#### URL

The websocket URL is accessed as `websocket.url`.

The property is actually a subclass of `str`, and also exposes all the
components that can be parsed out of the URL.

For example: `websocket.url.path`, `websocket.url.port`, `websocket.url.scheme`.

#### Headers

Headers are exposed as an immutable, case-insensitive, multi-dict.

For example: `websocket.headers['sec-websocket-version']`

#### Query Parameters

Query parameters are exposed as an immutable multi-dict.

For example: `websocket.query_params['search']`

#### Path Parameters

Router path parameters are exposed as a dictionary interface.

For example: `websocket.path_params['username']`

### Accepting the connection

* `await websocket.accept(subprotocol=None, headers=None)`

### Sending data

* `await websocket.send_text(data)`
* `await websocket.send_bytes(data)`
* `await websocket.send_json(data)`

JSON messages default to being sent over text data frames, from version 0.10.0 onwards.
Use `websocket.send_json(data, mode="binary")` to send JSON over binary data frames.

### Receiving data

* `await websocket.receive_text()`
* `await websocket.receive_bytes()`
* `await websocket.receive_json()`

May raise `starlette.websockets.WebSocketDisconnect()`.

JSON messages default to being received over text data frames, from version 0.10.0 onwards.
Use `websocket.receive_json(data, mode="binary")` to receive JSON over binary data frames.

### Iterating data

* `websocket.iter_text()`
* `websocket.iter_bytes()`
* `websocket.iter_json()`

Similar to `receive_text`, `receive_bytes`, and `receive_json` but returns an
async iterator.

```python hl_lines="7-8"
from starlette.websockets import WebSocket


async def app(scope, receive, send):
    websocket = WebSocket(scope=scope, receive=receive, send=send)
    await websocket.accept()
    async for message in websocket.iter_text():
        await websocket.send_text(f"Message text was: {message}")
    await websocket.close()
```

When `starlette.websockets.WebSocketDisconnect` is raised, the iterator will exit.

### Closing the connection

* `await websocket.close(code=1000, reason=None)`

### Sending and receiving messages

If you need to send or receive raw ASGI messages then you should use
`websocket.send()` and `websocket.receive()` rather than using the raw `send` and
`receive` callables. This will ensure that the websocket's state is kept
correctly updated.

* `await websocket.send(message)`
* `await websocket.receive()`

### Rejecting the connection

Before the calling `websocket.accept()` it is possible to reject the connection,
e.g. because of failing authentication.  The standard way to do this
is to call `websocket.close()` which will cause the ASGI web server
to respond to the initator with a HTTP 403 error.
It is also possible to construct a `Response` object and send that:

* `await websocket.send_response(response)`

If the ASGI server supports the `websocket.http.response` extension, this
will cause the specified response to be sent to the initiator, before closing
the connection.  Otherwise, it behaves like `websocket.close()`.
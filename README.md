<p align="center">
  <img width="320" height="192" src="https://raw.githubusercontent.com/encode/starlette/master/docs/starlette.png" alt='starlette'>
</p>
<p align="center">
    <em>✨ The little ASGI library that shines. ✨</em>
</p>
<p align="center">
<a href="https://travis-ci.org/encode/starlette">
    <img src="https://travis-ci.org/encode/starlette.svg?branch=master" alt="Build Status">
</a>
<a href="https://codecov.io/gh/encode/starlette">
    <img src="https://codecov.io/gh/encode/starlette/branch/master/graph/badge.svg" alt="Coverage">
</a>
<a href="https://pypi.org/project/starlette/">
    <img src="https://badge.fury.io/py/starlette.svg" alt="Package version">
</a>
</p>

---

Starlette is a small library for working with [ASGI](https://asgi.readthedocs.io/en/latest/).

It gives you `Request` and `Response` classes, websocket support, routing,
static files support, and a test client.

**Requirements:**

Python 3.6+

**Installation:**

```shell
pip3 install starlette
```

**Example:**

```python
from starlette.response import Response


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = Response('Hello, world!', media_type='text/plain')
        await response(receive, send)
```

You can run the application with any ASGI server, including [uvicorn](http://www.uvicorn.org/), [daphne](https://github.com/django/daphne/), or [hypercorn](https://pgjones.gitlab.io/hypercorn/).

<p align="center">&mdash; ⭐️ &mdash;</p>

---

## Contents

* [Responses](#responses)
    * [Response](#response)
    * [HTMLResponse](#htmlresponse)
    * [PlainTextResponse](#plaintextresponse)
    * [JSONResponse](#jsonresponse)
    * [RedirectResponse](#redirectresponse)
    * [StreamingResponse](#streamingresponse)
    * [FileResponse](#fileresponse)
* [Requests](#requests)
    * [Request](#request)
* [WebSockets](#websockets)
    * [WebSocketSession](#websocketsession)
* [Routing](#routing)
* [Static Files](#static-files)
* [Test Client](#test-client)
* [Debugging](#debugging)
* [Applications](#applications)

---

## Responses

Starlette includes a few response classes that handle sending back the
appropriate ASGI messages on the `send` channel.

### Response

Signature: `Response(content, status_code=200, headers=None, media_type=None)`

* `content` - A string or bytestring.
* `status_code` - An integer HTTP status code.
* `headers` - A dictionary of strings.
* `media_type` - A string giving the media type. eg. "text/html"

Starlette will automatically include a Content-Length header. It will also
include a Content-Type header, based on the media_type and appending a charset
for text types.

Once you've instantiated a response, you can send it by calling it as an
ASGI application instance.

```python
class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = Response('Hello, world!', media_type='text/plain')
        await response(receive, send)
```

### HTMLResponse

Takes some text or bytes and returns an HTML response.

```python
from starlette.response import HTMLResponse


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = HTMLResponse('<html><body><h1>Hello, world!</h1></body></html>')
        await response(receive, send)
```

### PlainTextResponse

Takes some text or bytes and returns an plain text response.

```python
from starlette.response import PlainTextResponse


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = PlainTextResponse('Hello, world!')
        await response(receive, send)
```

### JSONResponse

Takes some data and returns an `application/json` encoded response.

```python
from starlette.response import JSONResponse


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = JSONResponse({'hello': 'world'})
        await response(receive, send)
```

### RedirectResponse

Returns an HTTP redirect. Uses a 302 status code by default.

```python
from starlette.response import PlainTextResponse, RedirectResponse


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        if self.scope['path'] != '/':
            response = RedirectResponse(url='/')
        else:
            response = PlainTextResponse('Hello, world!')
        await response(receive, send)
```

### StreamingResponse

Takes an async generator and streams the response body.

```python
from starlette.request import Request
from starlette.response import StreamingResponse
import asyncio


async def slow_numbers(minimum, maximum):
    yield('<html><body><ul>')
    for number in range(minimum, maximum + 1):
        yield '<li>%d</li>' % number
        await asyncio.sleep(0.5)
    yield('</ul></body></html>')


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        generator = slow_numbers(1, 10)
        response = StreamingResponse(generator, media_type='text/html')
        await response(receive, send)
```

### FileResponse

Asynchronously streams a file as the response.

Takes a different set of arguments to instantiate than the other response types:

* `path` - The filepath to the file to stream.
* `headers` - Any custom headers to include, as a dictionary.
* `media_type` - A string giving the media type. If unset, the filename or path will be used to infer a media type.
* `filename` - If set, this will be included in the response `Content-Disposition`.

File responses will include appropriate `Content-Length`, `Last-Modified` and `ETag` headers.

```python
from starlette.response import FileResponse


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = FileResponse('/statics/favicon.ico')
        await response(receive, send)
```

---

## Requests

Starlette includes a `Request` class that gives you a nicer interface onto
the incoming request, rather than accessing the ASGI scope and receive channel directly.

### Request

Signature: `Request(scope, receive=None)`

```python
class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        request = Request(self.scope, receive)
        content = '%s %s' % (request.method, request.url.path)
        response = Response(content, media_type='text/plain')
        await response(receive, send)
```

Requests present a mapping interface, so you can use them in the same
way as a `scope`.

For instance: `request['path']` will return the ASGI path.

If you don't need to access the request body you can instantiate a request
without providing an argument to `receive`.

#### Method

The request method is accessed as `request.method`.

#### URL

The request URL is accessed as `request.url`.

The property is actually a subclass of `str`, and also exposes all the
components that can be parsed out of the URL.

For example: `request.url.path`, `request.url.port`, `request.url.scheme`.

#### Headers

Headers are exposed as an immutable, case-insensitive, multi-dict.

For example: `request.headers['content-type']`

#### Query Parameters

Headers are exposed as an immutable multi-dict.

For example: `request.query_params['abc']`

#### Body

There are a few different interfaces for returning the body of the request:

The request body as bytes: `await request.body()`

The request body, parsed as JSON: `await request.json()`

You can also access the request body as a stream, using the `async for` syntax:

```python
class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        request = Request(self.scope, receive)
        body = b''
        async for chunk in request.stream():
            body += chunk
        response = Response(body, media_type='text/plain')
        await response(receive, send)
```

If you access `.stream()` then the byte chunks are provided without storing
the entire body to memory. Any subsequent calls to `.body()` and `.json()` will
raise an error.


---

## WebSocket

Signature: `WebSocket(scope, recieve, send)`

```python
from starlette import WebSocket


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        ws = WebSocket(self.scope, receive, send)

        # Accept the connection
        await ws.connect()

        # Recive data
        name = await ws.receive()

        # Send text
        await ws.send('hello %s!' % name)

        # Send bytes
        await ws.send(b'hello world!')

        # Send JSON (as text)
        await ws.send_json({'data': 'hello world!', 'name': name})

        # Close the socket
        await ws.close()
```

Starlette includes a `WebSocket` class that gives you an interface
to incoming websocket connections, rather than accessing the ASGI scope, receive and send channels directly.

#### Request

The originating HTTP upgrade `Request` is accessed as `websocket.request`.

#### Subprotocols

The requested subprotocols parsed into a list are accessed as `websocket.Subprotocols`

#### State

The `WebSocket`'s state can be queried with the boolean attributes:  
`websocket.connected`  
`websocket.connecting`  
`websocket.closed`  

#### Connect
Signature: `websocket.connect(subprotocol=None, close=False, close_code=status.WS_1000_OK)`

Accept or reject an incoming WebSocket connection.  
Use `websocket.connect()` to accept a WebSocket connection request and set accepted
subprotocols(optional). You can easily reject a connection request using the `close=True` parameter
and send a specific close code with the `close_code` parameter.

#### Receive
Signature: `websocket.receive()`

Retreives the next WebSocket message. The result will be a string or byte array.

#### Receive_json
Signature: `websocket.receive(loads=None)`

Retreives the next WebSocket message and parses it as JSON. The result will be the parsed JSON as
native types.  
A user provided JSON parser function can provided with the `loads` parameter.

#### Send
Signature: `websocket.send(data)`

Send a WebSocket message. Accepted data types are `str` or `bytes`.

#### Send_json
Signature: `websocket.send_json(data, dumps=None, **kwargs)`

Send Python data as a WebSocket message encoded as a JSON string. This will create a `str` websocket message.  
A user provided JSON dump function can be provided with the `dumps` parameter and all extra
`**kwargs` will be passed to the `dumps` function.

#### Close
Signature: `websocket.close(code=status.WS_1000_OK)`

Close the WebSocket and optionally specifiy a status code, default is WS_1000_OK, to send with the
close message.


#### Status Codes

Status codes are available in the `status` object int the `websocket` module:  

```python
from starlette.websocket import status
# Available status codes:
status.WS_1000_OK
status.WS_1001_LEAVING
status.WS_1002_PROTOCOL_ERROR
status.WS_1003_UNSUPPORTED_TYPE
status.WS_1007_INALID_DATA
status.WS_1008_POLICY_VIOLATION
status.WS_1009_TOO_BIG
status.WS_1010_TLS_FAIL
```

---

## WebSockets

Starlette includes a `WebSocketSessions` class that fulfils a similar role
to the HTTP request, but that allows sending and receiving data on a websocket
session.

### WebSocketSession

Signature: `WebSocketSession(scope, receive=None, send=None)`

```python
from starlette.websockets import WebSocketSession


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        session = WebSocketSession(self.scope, receive=receive, send=send)
        await session.accept()
        await session.send_text('Hello, world!')
        await session.close()
```

Sessions present a mapping interface, so you can use them in the same
way as a `scope`.

For instance: `session['path']` will return the ASGI path.

#### URL

The session URL is accessed as `session.url`.

The property is actually a subclass of `str`, and also exposes all the
components that can be parsed out of the URL.

For example: `session.url.path`, `session.url.port`, `session.url.scheme`.

#### Headers

Headers are exposed as an immutable, case-insensitive, multi-dict.

For example: `session.headers['sec-websocket-version']`

#### Query Parameters

Headers are exposed as an immutable multi-dict.

For example: `session.query_params['abc']`

### Accepting the connection

* `await session.accept(subprotocol=None)`

### Sending data

* `await session.send_text(data)`
* `await session.send_bytes(data)`
* `await session.send_json(data)`

### Receiving data

* `await session.receive_text()`
* `await session.receive_bytes()`
* `await session.receive_json()`

May raise `starlette.websockets.Disconnect()`.

### Closing the connection

* `await session.close(code=1000)`

### Sending and receiving messages

If you need to send or receive raw ASGI messages then you should use
`session.send()` and `session.receive()` rather than using the raw `send` and
`receive` callables. This will ensure that the session's state is kept
correctly updated.

* `await session.send(message)`
* `await session.receive()`

---

## Routing

Starlette includes a `Router` class which is an ASGI application that
dispatches to other ASGI applications.

```python
from starlette.routing import Router, Path, PathPrefix
from myproject import Homepage, SubMountedApp


app = Router([
    Path('/', app=Homepage, methods=['GET']),
    PathPrefix('/mount/', app=SubMountedApp)
])
```

Paths can use URI templating style to capture path components.

```python
Path('/users/{username}', app=User, methods=['GET'])
```

Path components are made available in the scope, as `scope["kwargs"]`.

You can also use regular expressions for more complicated matching.

Named capture groups will be included in `scope["kwargs"]`:

```python
Path('/users/(?P<username>[a-zA-Z0-9_]{1,20})', app=User, methods=['GET'])
```

Because each target of the router is an ASGI instance itself, routers
allow for easy composition. For example:

```python
app = Router([
    Path('/', app=Homepage, methods=['GET']),
    PathPrefix('/users', app=Router([
        Path('/', app=Users, methods=['GET', 'POST']),
        Path('/{username}', app=User, methods=['GET']),
    ]))
])
```

The router will respond with "404 Not found" or "406 Method not allowed"
responses for requests which do not match.

### Protocol Routing

You can also route based on the incoming protocol, using the `ProtocolRouter`
class.

```python
from starlette.responses import Response
from starlette.routing import ProtocolRouter
from starlette.websockets import WebSocketSession


def http_endpoint(scope):
    return Response("Hello, world", media_type="text/plain")


def websocket_endpoint(scope):
    async def asgi(receive, send):
        session = WebSocketSession(scope, receive, send)
        await session.accept()
        await session.send_json({"hello": "world"})
        await session.close()
    return asgi


app = ProtocolRouter({
    "http": http_endpoint,
    "websocket": websocket_endpoint
})
```

---

## Static Files

As well as the `FileResponse` class, Starlette also includes ASGI applications
for serving a specific file or directory:

* `StaticFile(path)` - Serve a single file, given by `path`.
* `StaticFiles(directory)` - Serve any files in the given `directory`.

You can combine these ASGI applications with Starlette's routing to provide
comprehensive static file serving.

```python
from starlette.routing import Router, Path, PathPrefix
from starlette.staticfiles import StaticFile, StaticFiles


app = Router(routes=[
    Path('/', app=StaticFile(path='index.html')),
    PathPrefix('/static/', app=StaticFiles(directory='static')),
])
```

Static files will respond with "404 Not found" or "406 Method not allowed"
responses for requests which do not match.

---

## Test Client

The test client allows you to make requests against your ASGI application,
using the `requests` library.

```python
from starlette.response import HTMLResponse
from starlette.testclient import TestClient


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        response = HTMLResponse('<html><body>Hello, world!</body></html>')
        await response(receive, send)


def test_app():
    client = TestClient(App)
    response = client.get('/')
    assert response.status_code == 200
```

The test client exposes the same interface as any other `requests` session.
In particular, note that the calls to make a request are just standard
function calls, not awaitables.

### Testing WebSocket applications

You can also test websocket applications with the test client.

The `requests` library will be used to build the initial handshake, meaning you
can use the same authentication options and other headers between both http and
websocket testing.

```python
from starlette.testclient import TestClient
from starlette.websockets import WebSocketSession


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        session = WebSocketSession(self.scope, receive=receive, send=send)
        await session.accept()
        await session.send_text('Hello, world!')
        await session.close()


def test_app():
    client = TestClient(App)
    with client.websocket_connect('/') as session:
        data = session.receive_text()
        assert data == 'Hello, world!'
```

The operations on session are standard function calls, not awaitables.

It's important to use the session within a context-managed `with` block. This
ensure that the background thread on which the ASGI application is properly
terminated, and that any exceptions that occur within the application are
always raised by the test client.

#### Establishing a test session

* `.websocket_connect(url, subprotocols=None, **options)` - Takes the same set of arguments as `requests.get()`.

May raise `starlette.websockets.Disconnect` if the application does not accept the websocket connection.

#### Sending data

* `.send_text(data)` - Send the given text to the application.
* `.send_bytes(data)` - Send the given bytes to the application.
* `.send_json(data)` - Send the given data to the application.

#### Receiving data

* `.receive_text()` - Wait for incoming text sent by the application and return it.
* `.receive_bytes()` - Wait for incoming bytestring sent by the application and return it.
* `.receive_json()` - Wait for incoming json data sent by the application and return it.

May raise `starlette.websockets.Disconnect`.

#### Closing the connection

* `.close(code=1000)` - Perform a client-side close of the websocket connection.

---

## Debugging

You can use Starlette's `DebugMiddleware` to display simple error tracebacks in the browser.

```python
from starlette.debug import DebugMiddleware


class App:
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        raise RuntimeError('Something went wrong')


app = DebugMiddleware(App)
```

---

## Applications

Starlette also includes an `App` class that nicely ties together all of
its other functionality.

```python
from starlette.app import App
from starlette.response import PlainTextResponse
from starlette.staticfiles import StaticFiles


app = App()
app.mount("/static", StaticFiles(directory="static"))


@app.route('/')
def homepage(request):
    return PlainTextResponse('Hello, world!')


@app.route('/user/{username}')
def user(request, username):
    return PlainTextResponse('Hello, %s!' % username)


@app.websocket_route('/ws')
async def websocket_endpoint(session):
    await session.accept()
    await session.send_text('Hello, websocket!')
    await session.close()
```

### Adding routes to the application

You can use any of the following to add handled routes to the application:

* `.add_route(path, func, methods=["GET"])` - Add an HTTP route. The function may be either a coroutine or a regular function, with a signature like `func(request **kwargs) -> response`.
* `.add_websocket_route(path, func)` - Add a websocket session route. The function must be a coroutine, with a signature like `func(session, **kwargs)`.
* `.mount(prefix, app)` - Include an ASGI app, mounted under the given path prefix
* `.route(path)` - Add an HTTP route, decorator style.
* `.websocket_route(path)` - Add a WebSocket route, decorator style.

---

<p align="center"><i>Starlette is <a href="https://github.com/tomchristie/starlette/blob/master/LICENSE.md">BSD licensed</a> code.<br/>Designed & built in Brighton, England.</i><br/>&mdash; ⭐️ &mdash;</p>

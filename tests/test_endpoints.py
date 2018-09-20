import pytest
from starlette.responses import PlainTextResponse
from starlette.routing import Router, Path
from starlette.testclient import TestClient
from starlette.endpoints import HTTPEndpoint, WebSocketEndpoint


class Homepage(HTTPEndpoint):
    async def get(self, request, username=None):
        if username is None:
            return PlainTextResponse("Hello, world!")
        return PlainTextResponse(f"Hello, {username}!")


app = Router(routes=[Path("/", Homepage), Path("/{username}", Homepage)])

client = TestClient(app)


def test_http_endpoint_route():
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "Hello, world!"


def test_http_endpoint_route_kwargs():
    response = client.get("/tomchristie")
    assert response.status_code == 200
    assert response.text == "Hello, tomchristie!"


def test_http_endpoint_route_method():
    response = client.post("/")
    assert response.status_code == 405
    assert response.text == "Method Not Allowed"


def test_websocket_endpoint_on_connect():
    class WebSocketApp(WebSocketEndpoint):
        async def on_connect(self, websocket, **kwargs):
            assert websocket["subprotocols"] == ["soap", "wamp"]
            await websocket.accept(subprotocol="wamp")

    client = TestClient(WebSocketApp)
    with client.websocket_connect("/ws", subprotocols=["soap", "wamp"]) as websocket:
        assert websocket.accepted_subprotocol == "wamp"


def test_websocket_endpoint_on_receive():
    class WebSocketApp(WebSocketEndpoint):
        async def on_receive(self, websocket, **kwargs):
            _bytes = kwargs.get("bytes")
            if _bytes is not None:
                await websocket.send_bytes(b"Message bytes was: " + _bytes)
            _text = kwargs.get("text")
            if _text is not None:
                await websocket.send_text(f"Message text was: {_text}")

    client = TestClient(WebSocketApp)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_bytes(b"Hello, world!")
        _bytes = websocket.receive_bytes()
        assert _bytes == b"Message bytes was: Hello, world!"
        websocket.send_text("Hello, world!")
        _text = websocket.receive_text()
        assert _text == "Message text was: Hello, world!"


def test_websocket_endpoint_on_disconnect():
    class WebSocketApp(WebSocketEndpoint):
        async def on_disconnect(self, websocket, close_code):
            assert close_code == 1001
            await websocket.close(code=close_code)

    client = TestClient(WebSocketApp)
    with client.websocket_connect("/ws") as websocket:
        websocket.close(code=1001)

import json
import asyncio
from uuid import uuid4

import pytest

from starlette.websocket import WebSocket, WSState
from starlette.exceptions import WebSocketProtocolError
from starlette.testclient import TestClient, ASGIDataFaker


default_scope = {
    'type': 'websocket',
    'subprotocols': [],
}


def ws_setup(state=None, msgs=None):
    asgi = ASGIDataFaker(msgs)
    ws = WebSocket(default_scope, asgi.receive, asgi.send)

    if state:
        ws._state = state

    return (asgi, ws)


def ws_run(func, *args, **kwargs):
    loop = asyncio.new_event_loop()
    return loop.run_until_complete(func(*args, **kwargs))


#  def app(scope):
#      async def asgi(receive, send):
#          request = Request(scope, receive)
#          data = {"method": request.method, "url": request.url}
#          response = JSONResponse(data)
#          await response(receive, send)

#      return asgi


def test_bad_scope():
    asgi = ASGIDataFaker()

    with pytest.raises(WebSocketProtocolError) as e:
        WebSocket({}, asgi.receive, asgi.send)

    assert "Not a websocket scope" in e.value.detail


def test_initial_state():
    asgi = ASGIDataFaker()

    ws = WebSocket(default_scope, asgi.receive, asgi.send)
    assert ws.request._scope == default_scope
    assert ws._asgi_send == asgi.send
    assert ws._asgi_receive == asgi.receive
    assert ws._state == WSState.CLOSED
    assert ws.closed
    assert ws.subprotocols == []


def test_connect_not_closed():
    _, ws = ws_setup(state=WSState.CONNECTING)

    with pytest.raises(WebSocketProtocolError) as e:
        ws_run(ws.connect)

    assert ws.closed
    assert 'is not closed' in e.value.detail

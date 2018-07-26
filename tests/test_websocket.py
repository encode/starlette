import json
import asyncio
from uuid import uuid4

import pytest

from starlette.websocket import WebSocket, WSState, status
from starlette.exceptions import (
    WebSocketProtocolError,
    WebSocketNotConnected,
    WebSocketDisconnect
)
from starlette.testclient import TestClient, ASGIDataFaker
from starlette.utils import encode_json


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


# ### WebSocket instance tests ###
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


def test_connect_not_connect():
    # Connect doesn't get a connect message
    _, ws = ws_setup(msgs=[{'type': 'websocket.receive'}])

    with pytest.raises(WebSocketProtocolError) as e:
        ws_run(ws.connect)

    assert ws.closed
    assert 'Expected WebSocket `connection` but got: websocket.receive' in e.value.detail


def test_connect_close():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, close=True)

    assert ws.closed
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.close',
        'code': status.WS_1000_OK,
    }


def test_connect_close_with_code():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, close=True, close_code=status.WS_1001_LEAVING)

    assert ws.closed
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.close',
        'code': status.WS_1001_LEAVING,
    }


def test_connect_accept_subprotocol():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, subprotocol='v1.test.encode.io')

    assert asgi.sq.get_nowait() == {
        'type': 'websocket.accept',
        'subprotocol': 'v1.test.encode.io',
    }


def test_accept():
    asgi, ws = ws_setup(state=WSState.CONNECTING)

    ws_run(ws.accept)

    assert ws.connected
    assert asgi.sq.get_nowait() == {'type': 'websocket.accept'}


def test_accept_not_connecting():
    for state in (WSState.CLOSED, WSState.CONNECTED):
        _, ws = ws_setup(state=state)

        with pytest.raises(WebSocketProtocolError) as e:
            ws_run(ws.accept)

        assert ws._state == state
        assert 'Attempting to accept a WebSocket that is not connecting' in e.value.detail


def test_send_not_connected():
    _, ws = ws_setup(state=WSState.CLOSED)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.send, '')

    assert ws.closed
    assert 'WebSocket is not connected or open' in e.value.detail

    _, ws = ws_setup(state=WSState.CONNECTING)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.send, '')

    assert ws.connecting
    assert 'WebSocket is not connected or open' in e.value.detail


def test_send_text():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send, '{"json": "message"}')

    assert ws.connected
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'text':  '{"json": "message"}',
    }


def test_send_bytes():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send, b'{"json": "message"}')

    assert ws.connected
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'bytes':  b'{"json": "message"}',
    }


def test_send_json():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send_json, {"message": "payload"})

    assert ws.connected
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'text': '{"message":"payload"}'
    }


def test_receive_not_connected():
    for state in (WSState.CLOSED, WSState.CONNECTING):
        _, ws = ws_setup(state=state)

        with pytest.raises(WebSocketNotConnected) as e:
            ws_run(ws.receive)

        assert ws._state == state
        assert 'WebSocket is not connected or open' in e.value.detail


def test_receive_disconnect():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.disconnect',
            'code': status.WS_1001_LEAVING,
        }])

    with pytest.raises(WebSocketDisconnect) as e:
        ws_run(ws.receive)

    assert ws.closed
    assert e.value.status_code == status.WS_1001_LEAVING
    assert 'WebSocket has been disconnected' in e.value.detail


def test_receive_text():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  '{"json": "message"}',
        }])

    resp = ws_run(ws.receive)

    assert ws.connected
    assert resp == '{"json": "message"}'


def test_receive_bytes():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  b'{"json": "message"}',
        }])

    resp = ws_run(ws.receive)

    assert ws.connected
    assert resp == b'{"json": "message"}'


def test_receive_json():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  json.dumps({"message": "payload"}),
        }])

    resp = ws_run(ws.receive_json)

    assert ws.connected
    assert resp == {"message": "payload"}


def test_close_closed():
    _, ws = ws_setup(state=WSState.CLOSED)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.close)

    assert ws.closed
    assert 'WebSocket is not connected or open' in e.value.detail


def test_close():
    for state in (WSState.CONNECTED, WSState.CONNECTING):
        asgi, ws = ws_setup(state=state)

        ws_run(ws.close)
        asgi.sq.get_nowait() == {
            'type': 'websocket.close',
            'code': status.WS_1000_OK,
        }

        assert ws.closed


def test_close_codes():
    for state in (WSState.CONNECTED, WSState.CONNECTING):
        for code in (
            status.WS_1000_OK,
            status.WS_1001_LEAVING,
            status.WS_1002_PROT_ERROR,
            status.WS_1003_UNSUPPORTED_TYPE,
            status.WS_1007_INALID_DATA,
            status.WS_1008_POLICY_VIOLATION,
            status.WS_1009_TOO_BIG,
            status.WS_1010_TLS_FAIL,
        ):

            asgi, ws = ws_setup(state=state)

            ws_run(ws.close)
            asgi.sq.get_nowait() == {
                'type': 'websocket.close',
                'code': code,
            }

            assert ws.closed


# Some ASGI TestClient level tests
ws_headers = {
    'Upgrade': 'websocket',
    'Connection': 'upgrade',
    'Sec-WebSocket-Protocol': 'v1.test.encode.io',
}


def get_headers(client_headers=None):
    headers = ws_headers.copy()
    headers['Sec-WebSocket-Key'] = uuid4().hex

    if client_headers:
        headers.update(client_headers)

    return headers


def test_connect_accept():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect()
            assert ws.connected

        return asgi

    asgi_faker = ASGIDataFaker()
    client = TestClient(app, asgi_faker=asgi_faker)
    client.get("ws://connect/accept", headers=get_headers())

    assert asgi_faker.sq.get_nowait() == {
        'type': 'websocket.accept',
    }


def test_connect_accept_sub_proto():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect(subprotocol='test1.encode.io')
            assert ws.connected
            assert ws.request['subprotocols'] == ['test1.encode.io']
            assert ws.subprotocols == ['test1.encode.io']

        return asgi

    client = TestClient(app)
    response = client.get("ws://connect/accept/sub/proto/", headers=get_headers({
            'Sec-WebSocket-Protocol': 'test1.encode.io'
        }))

    assert response.text == ''


def test_connect_deny():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect(close=True)
            assert ws.closed

        return asgi

    client = TestClient(app)
    response = client.get('ws://connect/deny/', headers=get_headers())
    assert response.text == ''
    assert(response.status_code == 403)


def test_client_disconnect():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect()
            assert ws.connected

            with pytest.raises(WebSocketDisconnect) as e:
                await ws.receive()

            assert e.value.status_code == status.WS_1001_LEAVING
            assert 'WebSocket has been disconnected' in e.value.detail
            assert ws.closed

        return asgi

    client = TestClient(
        app,
        asgi_faker=ASGIDataFaker([
            {'type': 'websocket.connect'},
            {'type': 'websocket.disconnect', 'code': status.WS_1001_LEAVING},
        ])
    )

    client.get('ws://disconnect/', headers=get_headers())


def test_ping_pong():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect()
            assert ws.connected

            assert await ws.receive() == 'ping'

            await ws.send('pong')
            assert ws.connected

            await ws.close()
            assert ws.closed

        return asgi

    asgi_faker = ASGIDataFaker([
        {'type': 'websocket.connect'},
        {'type': 'websocket.receive', 'text': 'ping'}
    ])

    client = TestClient(app, asgi_faker=asgi_faker)
    client.get('ws://ping/pong/', headers=get_headers())

    assert asgi_faker.send_q.get_nowait() == {'type': 'websocket.accept'}
    assert asgi_faker.send_q.get_nowait() == {'type': 'websocket.send', 'text': 'pong'}


def test_ping_pong_kong():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect()
            assert ws.connected

            assert await ws.receive() == 'ping'

            await ws.send('pong')
            assert ws.connected

            await ws.send('kong')
            assert ws.connected

        return asgi

    asgi_faker = ASGIDataFaker([
        {'type': 'websocket.connect'},
        {'type': 'websocket.receive', 'text': 'ping'}
    ])

    client = TestClient(app, asgi_faker=asgi_faker)
    client.get('ws://ping/pong/kong', headers=get_headers())

    assert asgi_faker.send_q.get_nowait() == {'type': 'websocket.accept'}
    assert asgi_faker.send_q.get_nowait() == {'type': 'websocket.send', 'text': 'pong'}
    assert asgi_faker.send_q.get_nowait() == {'type': 'websocket.send', 'text': 'kong'}


def test_ping_pong_kong_json():
    def app(scope):
        async def asgi(receive, send):
            ws = WebSocket(scope, receive, send)
            await ws.connect()
            assert ws.connected

            assert await ws.receive_json() == {"play": "ping"}

            await ws.send_json({"play": "pong"})
            assert ws.connected

            await ws.send_json({"play": "kong"})
            assert ws.connected

        return asgi

    asgi_faker = ASGIDataFaker([
        {'type': 'websocket.connect'},
        {'type': 'websocket.receive', 'text': encode_json({"play": "ping"})}
    ])

    client = TestClient(app, asgi_faker=asgi_faker)
    client.get('ws://ping/pong/kong/json', headers=get_headers())

    assert asgi_faker.send_q.get_nowait() == {'type': 'websocket.accept'}
    assert asgi_faker.send_q.get_nowait() == {
        'type': 'websocket.send',
        'text': '{"play":"pong"}',
    }

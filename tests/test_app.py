from starlette import App
from starlette.response import PlainTextResponse
from starlette.testclient import TestClient


app = App()


@app.route('/func')
def func_homepage(request):
    return PlainTextResponse('Hello, world!')


@app.route('/async')
async def async_homepage(request):
    return PlainTextResponse('Hello, world!')


@app.websocket_route('/ws')
async def websocket_endpoint(session):
    await session.accept()
    await session.send_text('Hello, world!')
    await session.close()


client = TestClient(app)


def test_func_route():
    response = client.get('/func')
    assert response.status_code == 200
    assert response.text == 'Hello, world!'


def test_async_route():
    response = client.get('/async')
    assert response.status_code == 200
    assert response.text == 'Hello, world!'


def test_websocket_route():
    with client.wsconnect('/ws') as session:
        text = session.receive_text()
        assert text == 'Hello, world!'


def test_400():
    response = client.get('/404')
    assert response.status_code == 404

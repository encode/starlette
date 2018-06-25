from starlette import Response, Path, PathPrefix, Router, TestClient


def homepage(scope):
    return Response('Hello, world', media_type='text/plain')


def users(scope):
    return Response('All users', media_type='text/plain')


def user(scope):
    content = 'User ' + scope['kwargs']['username']
    return Response(content, media_type='text/plain')


app = Router([
    Path('/', app=homepage),
    PathPrefix('/users', app=Router([
        Path('', app=users),
        Path('/{username}', app=user),
    ]))
])


def test_router():
    client = TestClient(app)

    response = client.get('/')
    assert response.status_code == 200
    assert response.text == 'Hello, world'

    response = client.get('/foo')
    assert response.status_code == 404
    assert response.text == 'Not found'

    response = client.get('/users')
    assert response.status_code == 200
    assert response.text == 'All users'

    response = client.get('/users/tomchristie')
    assert response.status_code == 200
    assert response.text == 'User tomchristie'

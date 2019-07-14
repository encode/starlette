from starlette.status import (
    is_client_error,
    is_informational,
    is_redirect,
    is_server_error,
    is_success,
    is_teapot,
)


def test_is_informational():
    assert is_informational(102)
    assert not is_informational(204)


def test_is_success():
    assert is_success(201)
    assert not is_success(302)


def test_is_redirect():
    assert is_redirect(301)
    assert not is_redirect(200)


def test_is_client_error():
    assert is_client_error(404)
    assert not is_client_error(500)


def test_is_server_error():
    assert is_server_error(500)
    assert not is_server_error(401)


def test_is_teapot():
    """ Of course test is not a teapot. Nothing is teapot except for teapot. """
    assert is_teapot(418)
    assert not is_teapot(200)
    assert not is_teapot(301)
    assert not is_teapot(404)
    assert not is_teapot(500)

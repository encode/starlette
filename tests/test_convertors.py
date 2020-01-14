import pytest

from starlette.convertors import CONVERTOR_TYPES, Convertor, add, reset
from starlette.responses import Response
from starlette.routing import Router
from starlette.testclient import TestClient


class HexConvertor(Convertor):
    """Simple hex <-> bytes convertor for testing.
    """

    regex = r"[0-9A-Fa-f]+"

    def convert(self, value: str) -> bytes:
        return bytes.fromhex(value)

    def to_string(self, value: bytes) -> str:
        return value.hex()


@pytest.fixture(autouse=True)
def reset_convertors():
    yield
    reset()


def test_add_convertor():
    assert "hex" not in CONVERTOR_TYPES
    add("hex", HexConvertor())
    assert "hex" in CONVERTOR_TYPES


def test_unregistered_convertor():
    app = Router([])
    with pytest.raises(AssertionError) as ctx:
        app.route("/hex/{param:hex}", name="hex-convertor")(lambda r: None)

    assert str(ctx.value) == "Unknown path convertor 'hex'"


@pytest.fixture()
def app():
    add("hex", HexConvertor())

    app = Router([])

    @app.route("/hex/{param:hex}", name="hex-convertor")
    def hex_convertor(request):
        return Response(request.path_params["param"])

    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


def test_custom_convertor_not_match(client):
    resp = client.get("/hex/nothex")
    assert resp.status_code == 404


def test_custom_convertor_match(client):
    resp = client.get("/hex/deadbeef")
    assert resp.status_code == 200
    assert resp.content == b"\xde\xad\xbe\xef"


def test_custom_convertor_reverse(app):
    app.url_path_for("hex-convertor", param=b"\xde\xad\xbe\xef") == "/hex/deadbeef"

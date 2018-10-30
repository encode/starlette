from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.schemas import SchemaGenerator

app = Starlette()


@app.websocket_route("/ws")
def ws(session):
    """ws"""
    pass  # pragma: no cover


@app.route("/users", methods=["GET", "HEAD"])
def list_users(request):
    """list_users"""
    pass  # pragma: no cover


@app.route("/users", methods=["POST"])
def create_user(request):
    """create_user"""
    pass  # pragma: no cover


@app.route("/orgs")
class OrganisationsEndpoint(HTTPEndpoint):
    def get(self, request):
        """list_orgs"""
        pass  # pragma: no cover

    def post(self, request):
        """create_org"""
        pass  # pragma: no cover


def test_schema_generation():
    generator = SchemaGenerator()
    schema = generator.get_schema(app.routes)
    assert schema == {
        "/users": {"get": "list_users", "post": "create_user"},
        "/orgs": {"get": "list_orgs", "post": "create_org"},
    }

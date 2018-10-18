from starlette.graphql import GraphQLApp
from starlette.testclient import TestClient
import graphene


class Query(graphene.ObjectType):
    hello = graphene.String(name=graphene.String(default_value="stranger"))

    def resolve_hello(self, info, name):
        return "Hello " + name


schema = graphene.Schema(query=Query)
app = GraphQLApp(schema=schema)
client = TestClient(app)


def test_graphql_get():
    response = client.get("/?query={ hello }")
    assert response.status_code == 200
    assert response.json() == {"data": {"hello": "Hello stranger"}, "errors": None}


def test_graphql_post():
    response = client.post("/?query={ hello }")
    assert response.status_code == 200
    assert response.json() == {"data": {"hello": "Hello stranger"}, "errors": None}


def test_graphql_post_json():
    response = client.post("/", json={"query": "{ hello }"})
    assert response.status_code == 200
    assert response.json() == {"data": {"hello": "Hello stranger"}, "errors": None}


def test_graphql_post_graphql():
    response = client.post(
        "/", data="{ hello }", headers={"content-type": "application/graphql"}
    )
    assert response.status_code == 200
    assert response.json() == {"data": {"hello": "Hello stranger"}, "errors": None}


def test_graphql_post_invalid_media_type():
    response = client.post("/", data="{ hello }", headers={"content-type": "dummy"})
    assert response.status_code == 415
    assert response.text == "Unsupported Media Type"


def test_graphql_put():
    response = client.put("/", json={"query": "{ hello }"})
    assert response.status_code == 405
    assert response.text == "Method Not Allowed"


def test_graphql_no_query():
    response = client.get("/")
    assert response.status_code == 400
    assert response.text == "No GraphQL query found in the request"

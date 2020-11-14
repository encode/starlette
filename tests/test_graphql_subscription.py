from asyncio import sleep as asyncio_sleep
from random import randint

import graphene
import graphql
import pytest
from graphene import Int, ObjectType, Schema, String
from packaging import version

from starlette.routing import GraphQlSubscriptionRoute, Router
from starlette.testclient import TestClient


def test_minimal_versions():
    assert version.parse(graphene.__version__) >= version.parse("3.0b6")
    assert version.parse(graphql.__version__) > version.parse("3.0.0")


class Query(ObjectType):
    hello = String()

    def resolve_hello(root, info):
        return "Hello, world!"


class Subscription(ObjectType):
    count = Int(up_to=Int(default_value=2))

    async def subscribe_count(root, info, up_to):
        for i in range(1, up_to):
            yield i
            await asyncio_sleep(0.1)
        yield up_to


schema = Schema(query=Query, subscription=Subscription)
graphql_app = Router(
    routes=[
        GraphQlSubscriptionRoute("/graphql", schema=schema),
    ]
)


def assert_count_helper(session, upTo: int):
    for i in range(1, upTo + 1):
        result = session.receive_json()
        assert result["payload"]["data"]["count"] == i


def connection_ack_helper(session):
    session.send_json({"type": "connection_init", "payload": {}})
    result = session.receive_json()
    assert result == {"type": "connection_ack"}


def context_helper():
    context = TestClient(graphql_app)
    return context.websocket_connect("/graphql")


def test_subscribe_variable_one():
    with context_helper() as session:
        connection_ack_helper(session)
        graph = {
            "id": 30,
            "payload": {
                "query": "subscription($upTo: Int)" " { count(upTo: $upTo) }",
                "variables": {"upTo": 1},
            },
            "type": "data",
        }
        session.send_json(graph)
        assert_count_helper(session, 1)
        result = session.receive_json()
        assert result["type"] == "complete"
        assert result["id"] == 30


def test_subscribe_count_variable_3():
    with context_helper() as session:
        connection_ack_helper(session)
        graph = {
            "id": 30,
            "payload": {
                "query": "subscription($upTo: Int) { count(upTo: $upTo) }",
                "variables": {"upTo": 3},
            },
            "type": "data",
        }
        session.send_json(graph)
        assert_count_helper(session, 3)
        result = session.receive_json()
        assert result["type"] == "complete"
        assert result["id"] == 30


def test_subscribe_count_default_value():
    with context_helper() as session:
        connection_ack_helper(session)
        graph = {
            "id": 30,
            "type": "data",
            "payload": {
                "query": "subscription { count }",
            },
        }
        session.send_json(graph)
        assert_count_helper(session, 2)
        text = session.receive_json()
        assert text["type"] == "complete"
        assert text["id"] == 30


def test_invalid_query_subscribe():
    with context_helper() as session:
        connection_ack_helper(session)
        graph = {
            "id": 30,
            "payload": {"query": "subscription{ invalid }", "operationName": "Test"},
            "type": "data",
        }

        session.send_json(graph)
        result = session.receive_json()
        expected = {
            "payload": {
                "errors": [
                    {
                        "locations": [{"column": 15, "line": 1}],
                        "message": "Cannot query field 'invalid' on type "
                        "'Subscription'.",
                        "path": None,
                    }
                ]
            },
            "id": 30,
            "type": "error",
        }
        assert result == expected


def test_invalid_websocket_query():
    client = TestClient(graphql_app)
    response = client.get("/?query={ hello }")
    assert response.status_code == 404


def test_query_websocket():
    with context_helper() as session:
        connection_ack_helper(session)
        id = randint(10, 1000)
        graph = {
            "payload": {
                "query": "query Name { hello }",
            },
            "id": id,
            "type": "data",
        }
        session.send_json(graph)
        result = session.receive_json()
        assert "id" in result
        expected = {
            "payload": {"data": {"hello": "Hello, world!"}},
            "type": "data",
            "id": id,
        }
        assert result == expected


def test_query_error_websocket():
    with context_helper() as session:
        connection_ack_helper(session)
        id = randint(10, 1000)
        graph = {
            "payload": {
                "query": "{ unknown }",
            },
            "id": id,
            "type": "data",
        }
        session.send_json(graph)
        result = session.receive_json()
        assert "id" in result
        expected = {
            "payload": {
                "errors": [
                    {
                        "locations": [{"column": 3, "line": 1}],
                        "message": "Cannot query field 'unknown'" " on type 'Query'.",
                        "path": None,
                    }
                ]
            },
            "id": id,
            "type": "error",
        }
        assert result == expected


def test_query_aliases_websocket():
    with context_helper() as session:
        connection_ack_helper(session)
        id = randint(10, 1000)
        graph = {
            "payload": {
                "query": "query { id1: hello, id2: hello }",
            },
            "id": id,
            "type": "data",
        }
        session.send_json(graph)
        result = session.receive_json()
        assert "id" in result
        expected = {
            "payload": {"data": {"id1": "Hello, world!", "id2": "Hello, world!"}},
            "type": "data",
            "id": id,
        }
        assert result == expected


def test_wrong_schema():
    with pytest.raises(ValueError):
        Router(
            routes=[
                GraphQlSubscriptionRoute("/graphql", schema=None),
            ]
        )


def test_connection_disconnect():
    with context_helper() as session:
        connection_ack_helper(session)


def test_connection_close():
    with context_helper() as session:
        connection_ack_helper(session)
        graph = {
            "id": 30,
            "payload": {
                "query": "subscription($upTo: Int) { count(upTo: $upTo) }",
                "variables": {"upTo": 3},
            },
            "type": "data",
            "operationName": "toto",
        }
        session.send_json(graph)
        assert_count_helper(session, 1)
        session.close()

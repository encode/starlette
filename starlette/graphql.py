from starlette import status
from starlette.responses import PlainTextResponse, JSONResponse
from starlette.requests import Request
from starlette.types import ASGIInstance, Receive, Scope, Send
import functools
import typing

try:
    import graphene
    GrapheneSchema = graphene.Schema
except ImportError:  # pragma: nocover
    graphene = None  # type: ignore
    GrapheneSchema = typing.Any


class GraphQLApp:
    def __init__(self, schema: GrapheneSchema) -> None:
        self.schema = schema

    def __call__(self, scope: Scope) -> ASGIInstance:
        return functools.partial(self.asgi, scope=scope)

    async def asgi(self, receive: Receive, send: Send, scope: Scope) -> None:
        request = Request(scope, receive=receive)
        response = await self.handler(request)
        await response(receive, send)

    async def handler(self, request) -> None:
        if request.method == "GET":
            data = request.query_params  # type: typing.Mapping[str, typing.Any]

        elif request.method == "POST":
            content_type = request.headers.get("Content-Type", "")

            if "application/json" in content_type:
                data = await request.json()
            elif "application/graphql" in content_type:
                data = {"query": await request.body()}
            elif "query" in request.query_params:
                data = request.query_params
            else:
                return PlainTextResponse(
                    "Unsupported Media Type",
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                )

        else:
            return PlainTextResponse(
                "Method Not Allowed", status_code=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        try:
            query = data["query"]
            variables = data.get("variables")
        except KeyError:
            return PlainTextResponse(
                "No GraphQL query found in the request.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        result = self.schema.execute(query, variables)
        response_data = {"data": result.data, "errors": result.errors}
        status_code = (
            status.HTTP_400_BAD_REQUEST if result.errors else status.HTTP_200_OK
        )
        return JSONResponse(response_data, status_code=status_code)

    async def execute(self, query, variables=None):
        func = functools.partial(self.schema.execute, query=query, variables=variables)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(func)

import json
import typing

from starlette import status
from starlette.background import BackgroundTasks
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.types import Receive, Scope, Send

try:
    import graphene
    from graphql.error import GraphQLError, format_error as format_graphql_error
    from graphql.execution.executors.asyncio import AsyncioExecutor
except ImportError:  # pragma: nocover
    graphene = None
    AsyncioExecutor = None  # type: ignore
    format_graphql_error = None  # type: ignore
    GraphQLError = None  # type: ignore


class GraphQLApp:
    def __init__(
        self,
        schema: "graphene.Schema",
        executor: typing.Any = None,
        executor_class: type = None,
        graphiql: bool = True,
    ) -> None:
        self.schema = schema
        self.graphiql = graphiql
        if executor is None:
            # New style in 0.10.0. Use 'executor_class'.
            # See issue https://github.com/encode/starlette/issues/242
            self.executor = executor
            self.executor_class = executor_class
            self.is_async = executor_class is not None and issubclass(
                executor_class, AsyncioExecutor
            )
        else:
            # Old style. Use 'executor'.
            # We should remove this in the next median/major version bump.
            self.executor = executor
            self.executor_class = None
            self.is_async = isinstance(executor, AsyncioExecutor)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.executor is None and self.executor_class is not None:
            self.executor = self.executor_class()

        request = Request(scope, receive=receive)
        response = await self.handle_graphql(request)
        await response(scope, receive, send)

    async def handle_graphql(self, request: Request) -> Response:
        if request.method in ("GET", "HEAD"):
            if "text/html" in request.headers.get("Accept", ""):
                if not self.graphiql:
                    return PlainTextResponse(
                        "Not Found", status_code=status.HTTP_404_NOT_FOUND
                    )
                return await self.handle_graphiql(request)

            data = request.query_params  # type: typing.Mapping[str, typing.Any]

        elif request.method == "POST":
            content_type = request.headers.get("Content-Type", "")

            if "application/json" in content_type:
                data = await request.json()
            elif "application/graphql" in content_type:
                body = await request.body()
                text = body.decode()
                data = {"query": text}
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
            operation_name = data.get("operationName")
        except KeyError:
            return PlainTextResponse(
                "No GraphQL query found in the request",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        background = BackgroundTasks()
        context = {"request": request, "background": background}

        result = await self.execute(
            query, variables=variables, context=context, operation_name=operation_name
        )
        error_data = (
            [format_graphql_error(err) for err in result.errors]
            if result.errors
            else None
        )
        response_data = {"data": result.data}
        if error_data:
            response_data["errors"] = error_data
        status_code = (
            status.HTTP_400_BAD_REQUEST if result.errors else status.HTTP_200_OK
        )

        return JSONResponse(
            response_data, status_code=status_code, background=background
        )

    async def execute(  # type: ignore
        self, query, variables=None, context=None, operation_name=None
    ):
        if self.is_async:
            return await self.schema.execute(
                query,
                variables=variables,
                operation_name=operation_name,
                executor=self.executor,
                return_promise=True,
                context=context,
            )
        else:
            return await run_in_threadpool(
                self.schema.execute,
                query,
                variables=variables,
                operation_name=operation_name,
                context=context,
            )

    async def handle_graphiql(self, request: Request) -> Response:
        text = GRAPHIQL.replace("{{REQUEST_PATH}}", json.dumps(request.url.path))
        return HTMLResponse(text)


# GraphiQL example from https://github.com/graphql/graphiql/blob/main/examples/graphiql-cdn/index.html
# Modified to enable header edition using content from https://github.com/graphql/graphiql/issues/59#issuecomment-643688951
GRAPHIQL = """
<!--
 *  Copyright (c) 2020 GraphQL Contributors
 *  All rights reserved.
 *
 *  This source code is licensed under the license found in the
 *  LICENSE file in the root directory of this source tree.
-->
<!DOCTYPE html>
<html>
  <head>
    <style>
      body {
        height: 100%;
        margin: 0;
        width: 100%;
        overflow: hidden;
      }

      #graphiql {
        height: 100vh;
      }
    </style>

    <!--
      This GraphiQL example depends on Promise and fetch, which are available in
      modern browsers, but can be "polyfilled" for older browsers.
      GraphiQL itself depends on React DOM.
      If you do not want to rely on a CDN, you can host these files locally or
      include them directly in your favored resource bunder.
    -->
    <script
      crossorigin
      src="https://unpkg.com/react@16/umd/react.production.min.js"
    ></script>
    <script
      crossorigin
      src="https://unpkg.com/react-dom@16/umd/react-dom.production.min.js"
    ></script>

    <!--
      These two files can be found in the npm module, however you may wish to
      copy them directly into your environment, or perhaps include them in your
      favored resource bundler.
     -->
    <link rel="stylesheet" href="https://unpkg.com/graphiql/graphiql.min.css" />
  </head>

  <body>
    <div id="graphiql">Loading...</div>
    <script
      src="https://unpkg.com/graphiql/graphiql.min.js"
      type="application/javascript"
    ></script>
    <script src="/renderExample.js" type="application/javascript"></script>
    <script>
      function graphQLFetcher(graphQLParams, opts = { headers: {} }) {
        return fetch(
          {{REQUEST_PATH}},
          {
            method: 'post',
            headers: Object.assign({
              Accept: 'application/json',
              'Content-Type': 'application/json',
            }, opts.headers),
            body: JSON.stringify(graphQLParams),
          },
        ).then(function (response) {
          return response.json().catch(function () {
            return response.text();
          });
        });
      }

      ReactDOM.render(
        React.createElement(GraphiQL, {
          fetcher: graphQLFetcher,
          headerEditorEnabled: true,
          headers: '{"authorization": "Bearer jnjlojokiklk"}',
          defaultVariableEditorOpen: true,
        }),
        document.getElementById('graphiql'),
      );
    </script>
  </body>
</html>
"""  # noqa: E501

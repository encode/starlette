Starlette has a simple but capable request routing system. A routing table
is defined as a list of routes, and passed when instantiating the application.

```python
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def homepage(request):
    return PlainTextResponse("Homepage")

async def about(request):
   return PlainTextResponse("About")


routes = [
    Route("/", endpoint=homepage),
    Route("/about", endpoint=about),
]

app = Starlette(routes=routes)
```

The `endpoint` argument can be one of:

* A regular function or async function, which accepts a single `request`
argument and which should return a response.
* A class that implements the ASGI interface, such as Starlette's [class based
views](endpoints.md).

## Path Parameters

Paths can use URI templating style to capture path components.

```python
Route('/users/{username}', endpoint=user)
```

Convertors for `int`, `float`, and `path` are also available:

```python
Route('/users/{user_id:int}', endpoint=user)
```

Path parameters are made available in the request, as the `request.path_params`
dictionary.

```python
async def user(request):
    user_id = request.path_params['user_id']
    ...
```

## Handling HTTP methods

Routes can also specify which HTTP methods are handled by an endpoint:

```python
Route('/users/{user_id:int}', endpoint=user, methods=["GET", "POST"])
```

By default function endpoints will only accept `GET` requests, unless specified.

## Submounting routes

In large applications you might find that you want to break out parts of the
routing table, based on a common path prefix.

```python
routes = [
    Route('/', endpoint=homepage),
    Mount('/users', routes=[
        Route('/', endpoint=users, methods=['GET', 'POST']),
        Route('/{username}', endpoint=user),
    ])
]
```

This style allows you to define different subsets of the routing table in
different parts of your project.

```python
from myproject import users, auth

routes = [
    Route('/', endpoint=homepage),
    Mount('/users', routes=users.routes),
    Mount('/auth', routes=auth.routes),
]
```

You can also use mounting to include sub-applications within your Starlette
application. For example...

```python
# This is a standalone static files server:
app = StaticFiles(directory="static")

# This is a static files server mounted within a Starlette application,
# underneath the "/static" path.
routes = [
    ...
    Mount("/static", StaticFiles(directory="static"), name="static")
]

app = Starlette(routes=routes)
```

## Route priority

Incoming paths are matched against each `Route` in order.

In cases where more that one route could match an incoming path, you should
take care to ensure that more specific routes are listed before general cases.

For example:

```python
# Don't do this: `/users/me` will never match incoming requests.
routes = [
    Route('/users/{username}', endpoint=user),
    Route('/users/me', endpoint=current_user),
]

# Do this: `/users/me` is tested first.
routes = [
    Route('/users/me', endpoint=current_user),
    Route('/users/{username}', endpoint=user),
]
```

## Working with Router instances

If you're working at a low-level you might want to use a plain `Router`
instance, rather that creating a `Starlette` application. This gives you
a lightweight ASGI application that just provides the application routing,
without wrapping it up in any middleware.

```python
app = Router(routes=[
    Route('/', endpoint=homepage),
    Mount('/users', routes=[
        Route('/', endpoint=users, methods=['GET', 'POST']),
        Route('/{username}', endpoint=user),
    ])
])
```

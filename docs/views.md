
Starlette includes a `View` class that provides a class-based view pattern which
handles HTTP method dispatching and provides additional structure for HTTP views.

```python
from starlette import PlainTextResponse
from starlette.app import App
from starlette.views import View


app = App()


class HomepageView(View):
    async def get(self, request, **kwargs):
        response = PlainTextResponse(f"Hello, world!")
        return response


class UserView(View):
    async def get(self, request, **kwargs):
        username = kwargs.get("username")
        response = PlainTextResponse(f"Hello, {username}")
        return response


app.add_route("/", HomepageView())
app.add_route("/user/{username}", UserView())
```

Class-based views will respond with "404 Not found" or "406 Method not allowed"
responses for requests which do not match.

import typing

from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse
from starlette.types import Receive, Scope, Send

try:
    import jinja2
except ImportError:  # pragma: nocover
    jinja2 = None  # type: ignore


class _TemplateResponse(HTMLResponse):
    def __init__(
        self,
        template: typing.Any,
        context: dict,
        status_code: int = 200,
        headers: dict = None,
        media_type: str = HTMLResponse.media_type,
        background: BackgroundTask = None,
    ):
        self.template = template
        self.context = context
        self.status_code = status_code
        self.background = background
        self.base_headers = headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = self.context.get("request", {})
        extensions = request.get("extensions", {})
        if "http.response.template" in extensions:
            await send(
                {
                    "type": "http.response.template",
                    "template": self.template,
                    "context": self.context,
                }
            )
        content = await self.template.render_async(self.context)
        self.body = self.render(content)
        self.init_headers(self.base_headers)
        await super().__call__(scope, receive, send)


class Jinja2Templates:
    """
    templates = Jinja2Templates("templates")

    return templates.TemplateResponse("index.html", {"request": request})
    """

    def __init__(self, directory: str) -> None:
        assert jinja2 is not None, "jinja2 must be installed to use Jinja2Templates"
        self.env = self.get_env(directory)

    def get_env(self, directory: str) -> "jinja2.Environment":
        @jinja2.contextfunction
        def url_for(context: dict, name: str, **path_params: typing.Any) -> str:
            request = context["request"]
            return request.url_for(name, **path_params)

        loader = jinja2.FileSystemLoader(directory)
        env = jinja2.Environment(loader=loader, autoescape=True, enable_async=True)
        env.globals["url_for"] = url_for
        return env

    def get_template(self, name: str) -> "jinja2.Template":
        return self.env.get_template(name)

    def TemplateResponse(
        self,
        name: str,
        context: dict,
        status_code: int = 200,
        headers: dict = None,
        media_type: str = HTMLResponse.media_type,
        background: BackgroundTask = None,
    ) -> _TemplateResponse:
        if "request" not in context:
            raise ValueError('context must include a "request" key')
        template = self.get_template(name)
        return _TemplateResponse(
            template,
            context,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )

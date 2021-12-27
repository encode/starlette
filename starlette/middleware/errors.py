import asyncio
import hashlib
import html
import inspect
import os
import sys
import traceback
import typing
from pprint import pformat

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

STYLES = """
:root {
    --red: rgb(239 68 68);
    --yellow-lightest: rgb(254 249 195);
    --gray: rgb(17 24 39);
    --gray-light: rgb(107 114 128);
    --gray-lighter: rgb(229 231 235);
    --gray-lightest: rgb(243 244 246);
}

html,
body {
    font-size: 14px;
    line-height: 1.6;
    background: #fff;
    padding: 0;
    margin: 0;
    color: var(--gray);
    background: var(--gray-lightest);
    font-family: Inter var, ui-sans-serif, system-ui,
        -apple-system, BlinkMacSystemFont, Segoe UI, Roboto,
        Helvetica Neue, Arial, Noto Sans, sans-serif, Apple Color Emoji,
        Segoe UI Emoji, Segoe UI Symbol, Noto Color Emoji;
}

.text-muted {
    color: var(--gray-light);
}

.bg-white {
    background-color: white;
}

pre {
    font-family: consolas, monospace;
    margin: 0;
}

.header {
    padding: 48px 48px 0 48px;
    color: var(--gray-light);
}

.exception-class {
    color: var(--red);
}

.exception {
    font-size: 1.5rem;
    color: var(--red);
}

section {
    padding: 24px 48px;
}

section.trace {
    padding-top: 48px;
    padding-bottom: 48px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 24px;
}

.snippet-wrapper {
    display: none;
}
.snippet-wrapper.current {
    display: block;
}

.snippet {
    background-color: white;
    padding: 0 16px;
}

.snippet header {
    padding: 16px 0;
    border-bottom: 1px solid var(--gray-lightest);
}

.snippet footer {
    padding: 16px 0;
    border-top: 1px solid var(--gray-lightest);
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--gray-light);
}

.snippet pre {
    margin: 2px 0;
    white-space: pre-wrap;
    overflow-x: auto;
    overflow-wrap: anywhere;
}

.snippet .line {
    display: flex;
    overflow-x: auto;
    overflow-wrap: normal;
}

.snippet .line.highlight {
    background-color: var(--yellow-lightest);
}

.snippet .line-number {
    text-align: right;
    width: 48px;
    margin-right: 24px;
    color: var(--gray-light);
    flex-shrink: 0;
}

.snippet .code {
    flex: auto;
}

.frames .frame {
    display: flex;
    align-items: center;
    background-color: transparent;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
    gap: 12px;
    margin-bottom: 4px;
}

.frames .frame:hover {
    background-color: var(--gray-lighter);
}

.frames .frame.current {
    background-color: white;
}

.dot {
    height: 10px;
    width: 10px;
    border-radius: 100%;
    background-color: var(--gray-light);
}

.dot-red {
    background-color: var(--red);
}

details {
    margin-bottom: 16px;
}

summary {
    cursor: pointer;
}

dl {
    display: grid;
    grid-template-columns: repeat(12, minmax(0, 1fr));
    align-items: center;
    margin: 0;
    padding: 4px;
    border-top: 1px solid var(--gray-lighter);
}

dl:first-of-type {
    margin-top: 16px;
}

dl:hover {
    background-color: var(--gray-lightest);
}

dt {
    color: var(--gray-light);
    text-overflow: ellipsis;
    grid-column: span 2 / span 2;
}

dd {
    flex: auto;
    grid-column: span 10 / span 10;
    overflow-x: auto;
}

.locals {
    padding: 2px;
}

.locals:hover {
    background-color: transparent;
}

.locals dt {
    padding: 2px;
}

.locals dd {
    flex: auto;
    overflow-x: auto;
    padding: 2px 8px;
    background-color: var(--gray-lightest);
}

@media(max-width: 1200px) {
    section {
        padding: 12px 16px;
    }

    section.trace {
        grid-template-columns: repeat(1, minmax(0, 1fr));
    }

    dl {
        grid-template-columns: repeat(1, minmax(0, 1fr));
    }

    dd {
        margin-inline-start: 0px;
    }

    .package-dir {
        display: none;
    }
}

"""

JS = """
<script type="text/javascript">
    Array.from(document.querySelectorAll('[id^="switch"]')).forEach(function(el) {
        el.addEventListener('click', function() {
            var current = document.querySelector('.snippet-wrapper.current');
            if (current) {
                current.classList.remove('current');
            }

            var frameIndex = el.dataset.frameIndex;
            var target = document.querySelector('#snippet-' + frameIndex);
            if (target) {
                target.classList.add('current');
            }

            var currentSwitch = document.querySelector('.frame.current');
            if (currentSwitch) {
                currentSwitch.classList.remove('current');
            }
            el.classList.add('current')
        });
    });
</script>
"""

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <title>{exception}: {error} | Starlette Debugger</title>
        <meta name="viewport" content="width=device-width">
        <style type='text/css'>
            {styles}
        </style>
    </head>
    <body>
        {header}
        <main>
            <section class="trace">
                {code_snippet}
                <div class="frames">
                {frames}
                </div>
            </section>
            <section class="bg-white">
                {request}
                {headers}
                {session}
                {cookies}
                {request_state}
                {app_state}
                {platform}
                {environment}
            </section>
        </main>
        {js}
    </body>
</html>
"""

HEADER_TEMPLATE = """
<header class="header">
    <div>
        <b class="exception-class">{exception_class}</b> at {method} {path}
    </div>
    <div class="exception text-red">{message}</div>
</header>
"""

LOCALS_ROW_TEMPLATE = """
<dl class="locals">
    <dt>{name}</dt>
    <dd><pre>{value}</pre></dd>
</dl>
"""

CODE_LINE_TEMPLATE = """
<pre class="line {highlight}">
    <div class="line-number">{line_number}</div>
    <div class="code">{line}</div>
</pre>
"""

CODE_TEMPLATE = """
<div id="snippet-{id}" class="snippet-wrapper{extra_css_class}">
    <div class="snippet">
        <header>
            <b><span class="package-dir">{package_dir}</span>{relative_path}</b>
        </header>
        <div>
            {lines}
        </div>
        {locals}
        <footer>
            <div class="symbol">{package}.{symbol}</div>
            <div class="package">{package}</div>
        </footer>
    </div>
</div>
"""

FRAME_LINE_TEMPLATE = """
<div class="frame {extra_css_class}" id="switch-{id}" data-frame-index="{id}">
    <div class="dot{dot}"></div>
    <div>
        <span class="text-muted">{package}</span>
        <span title="{file_path}">{file_name}<span>
        <span class="text-muted">in</span>
        <span class="symbol">{symbol}</span>
        <span class="text-muted">at line</span> {line_number}
    </div>
</div>
"""

DETAILS_ROW_TEMPLATE = """
<dl>
    <dt>{label}</dt>
    <dd>{value}</dd>
</dl>
"""

DETAILS_TEMPLATE = """
<details {open}>
    <summary>{label}</summary>
    {rows}
</details>
"""


def get_relative_filename(path: str) -> str:
    for sys_path in reversed(sorted(sys.path)):
        if sys_path in path:
            path = path.replace(sys_path + "/", "")
            break
    return path


def format_qual_name(obj: typing.Any) -> str:
    if inspect.isclass(obj):
        module_name = obj.__module__
        type_name = obj.__name__
    else:
        module_name = obj.__class__.__module__
        type_name = obj.__class__.__name__

    if module_name == "builtins":
        module_name = ""
    if module_name:
        return f"{module_name}.{type_name}"
    return type_name


def frame_id(frame: inspect.FrameInfo) -> str:
    hash = hashlib.md5()
    hash.update(f"{frame.filename}{frame.lineno}".encode())
    return hash.hexdigest()


def is_vendor(frame: inspect.FrameInfo) -> bool:
    return sys.exec_prefix in frame.filename


def get_package_name(frame: inspect.FrameInfo) -> str:
    return frame.frame.f_globals["__package__"].split(".")[0]


def get_symbol(frame: inspect.FrameInfo) -> str:
    symbol = ""
    if "self" in frame.frame.f_locals:
        symbol = frame.frame.f_locals["self"].__class__.__name__

    if "cls" in frame.frame.f_locals:
        symbol = frame.frame.f_locals["cls"].__name__

    # if we cannot detect class name then just a method name will be rendered
    function = frame.function
    if symbol:
        function = symbol + "." + function
    return function


def mask_secrets(key: str, value: str) -> str:
    key = key.lower()
    if any(
        [
            "key" in key,
            "token" in key,
            "password" in key,
            "secret" in key,
        ]
    ):
        return "*" * 8
    return value


class ServerErrorMiddleware:
    """
    Handles returning 500 responses when a server error occurs.

    If 'debug' is set, then traceback responses will be returned,
    otherwise the designated 'handler' will be called.

    This middleware class should generally be used to wrap *everything*
    else up, so that unhandled exceptions anywhere in the stack
    always result in an appropriate 500 response.
    """

    def __init__(
        self, app: ASGIApp, handler: typing.Callable = None, debug: bool = False
    ) -> None:
        self.app = app
        self.handler = handler
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message: Message) -> None:
            nonlocal response_started, send

            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            if not response_started:
                request = Request(scope)
                if self.debug:
                    # In debug mode, return traceback responses.
                    response = self.debug_response(request, exc)
                elif self.handler is None:
                    # Use our default 500 error handler.
                    response = self.error_response(request, exc)
                else:
                    # Use an installed 500 error handler.
                    if asyncio.iscoroutinefunction(self.handler):
                        response = await self.handler(request, exc)
                    else:
                        response = await run_in_threadpool(self.handler, request, exc)

                await response(scope, receive, send)

            # We always continue to raise the exception.
            # This allows servers to log the error, or allows test clients
            # to optionally raise the error within the test case.
            raise exc

    def format_line(
        self, index: int, line: str, frame_lineno: int, frame_index: int
    ) -> str:
        return CODE_LINE_TEMPLATE.format(
            line=html.escape(line).replace(" ", "&nbsp"),
            line_number=(frame_lineno - frame_index) + index,
            highlight=" highlight" if index == frame_index else "",
        )

    def generate_frame_html(self, frame: inspect.FrameInfo, is_collapsed: bool) -> str:
        symbol = get_symbol(frame)
        extra_css_classes = []
        if not is_collapsed:
            extra_css_classes.append("current")
        if is_vendor(frame):
            extra_css_classes.append("vendor")

        return FRAME_LINE_TEMPLATE.format(
            id=frame_id(frame),
            dot="" if is_vendor(frame) else " dot-red",
            package="{package} &middot;".format(package=get_package_name(frame))
            if is_vendor(frame)
            else "",
            file_path=html.escape(frame.filename),
            file_name=html.escape(get_relative_filename(frame.filename)),
            symbol=symbol,
            line_number=frame.lineno,
            extra_css_class=" ".join(extra_css_classes),
        )

    def generate_locals_for_frame(self, frame: inspect.FrameInfo) -> str:
        return "".join(
            LOCALS_ROW_TEMPLATE.format(
                name=var_name, value=html.escape(pformat(var_value, indent=2))
            )
            for var_name, var_value in frame.frame.f_locals.items()
        )

    def generate_snippet_for_frame(
        self, frame: inspect.FrameInfo, is_collapsed: bool
    ) -> str:
        code_context = "".join(
            self.format_line(index, line, frame.lineno, frame.index)  # type: ignore
            for index, line in enumerate(frame.code_context or [])
        )

        return CODE_TEMPLATE.format(
            id=frame_id(frame),
            package_dir=frame.filename.replace(
                get_relative_filename(frame.filename), ""
            ),
            relative_path=html.escape(get_relative_filename(frame.filename)),
            file_path=html.escape(frame.filename),
            lines=code_context,
            extra_css_class="" if is_collapsed else " current",
            locals=self.generate_locals_for_frame(frame),
            symbol=get_symbol(frame),
            package=get_package_name(frame),
        )

    def render_details_row(self, data: typing.Mapping) -> str:
        row_html = ""
        for name, value in data.items():
            row_html += DETAILS_ROW_TEMPLATE.format(
                label=name, value=mask_secrets(name, value)
            )

        if not row_html:
            row_html = "<dl><dt>empty</dt><dd></dd></dl>"
        return row_html

    def generate_request_details_html(self, request: Request) -> str:
        return DETAILS_TEMPLATE.format(
            label="Request",
            rows=self.render_details_row(
                {
                    "Method": request.method,
                    "Path": request.url.path,
                    "Path params": "<br>".join(
                        [
                            f'<span class="text-muted">{k}</span> = {v}'
                            for k, v in request.path_params.items()
                        ]
                    ),
                    "Query params": "<br>".join(
                        [
                            f'<span class="text-muted">{k}</span> = {v}'
                            for k, v in request.query_params.items()
                        ]
                    ),
                    "Content type": request.headers.get("Content-Type", ""),
                    "Client": f"{request.client.host}:{request.client.port}",
                },
            ),
            open="open",
        )

    def generate_headers_html(self, request: Request) -> str:
        return DETAILS_TEMPLATE.format(
            label="Headers",
            rows=self.render_details_row(request.headers),
            open="",
        )

    def generate_cookies_html(self, request: Request) -> str:
        return DETAILS_TEMPLATE.format(
            label="Cookies",
            rows=self.render_details_row(request.cookies),
            open="",
        )

    def generate_session_html(self, request: Request) -> str:
        if "session" in request.scope:
            return DETAILS_TEMPLATE.format(
                label="Session",
                rows=self.render_details_row(request.headers),
                open="",
            )
        return ""

    def generate_environment_html(self, request: Request) -> str:
        return DETAILS_TEMPLATE.format(
            label="Environment",
            rows=self.render_details_row(os.environ),
            open="",
        )

    def generate_platform_html(self, request: Request) -> str:
        return DETAILS_TEMPLATE.format(
            label="Platform",
            rows=self.render_details_row(
                {
                    "Python version": sys.version,
                    "Platform": sys.platform,
                    "Python": sys.executable,
                    "Paths": "<br>".join(sys.path),
                }
            ),
            open="",
        )

    def generate_request_state_html(self, request: Request) -> str:
        return DETAILS_TEMPLATE.format(
            label="Request state",
            rows=self.render_details_row(
                {k: v for k, v in request.state._state.items()}
            ),
            open="",
        )

    def generate_app_state_html(self, request: Request) -> str:
        if "app" in request.scope:
            return DETAILS_TEMPLATE.format(
                label="App state",
                rows=self.render_details_row(
                    {k: v for k, v in request.app.state._state.items()}
                ),
                open="",
            )
        return ""

    def generate_html(self, request: Request, exc: Exception, limit: int = 7) -> str:
        traceback_obj = traceback.TracebackException.from_exception(
            exc, capture_locals=True
        )

        header_html = HEADER_TEMPLATE.format(
            exception_class=format_qual_name(traceback_obj.exc_type),
            method=request.method,
            message=html.escape(str(exc) or '""'),
            path=request.url.path,
        )

        frames_html = ""
        code_html = ""
        is_collapsed = False
        exc_traceback = exc.__traceback__
        if exc_traceback is not None:
            frames = inspect.getinnerframes(exc_traceback, limit)
            for frame in reversed(frames):
                frames_html += self.generate_frame_html(frame, is_collapsed)
                code_html += self.generate_snippet_for_frame(frame, is_collapsed)
                is_collapsed = True

        return TEMPLATE.format(
            styles=STYLES,
            js=JS,
            header=header_html,
            code_snippet=code_html,
            frames=frames_html,
            exception=traceback_obj.exc_type.__name__,
            error=html.escape(str(traceback_obj)),
            request_state=self.generate_request_state_html(request),
            app_state=self.generate_app_state_html(request),
            platform=self.generate_platform_html(request),
            request=self.generate_request_details_html(request),
            headers=self.generate_headers_html(request),
            session=self.generate_session_html(request),
            cookies=self.generate_cookies_html(request),
            environment=self.generate_environment_html(request),
        )

    def generate_plain_text(self, exc: Exception) -> str:
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def debug_response(self, request: Request, exc: Exception) -> Response:
        accept = request.headers.get("accept", "")

        if "text/html" in accept:
            content = self.generate_html(request, exc)
            return HTMLResponse(content, status_code=500)
        content = self.generate_plain_text(exc)
        return PlainTextResponse(content, status_code=500)

    def error_response(self, request: Request, exc: Exception) -> Response:
        return PlainTextResponse("Internal Server Error", status_code=500)

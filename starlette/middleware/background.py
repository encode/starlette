from typing import List

from starlette.background import BackgroundTask
from starlette.types import ASGIApp, Receive, Scope, Send


class BackgroundTaskMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        tasks: "List[BackgroundTask]" = []
        scope["starlette.background"] = tasks = []
        try:
            await self._app(scope, receive, send)
        finally:
            for task in tasks:
                await task()

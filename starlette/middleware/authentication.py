import functools

from starlette.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.types import ASGIApp, ASGIInstance, Receive, Scope, Send


class AuthenticationMiddleware:
    def __init__(self, app: ASGIApp, backend: AuthenticationBackend) -> None:
        self.app = app
        self.backend = backend

    def __call__(self, scope: Scope) -> ASGIInstance:
        return functools.partial(self.asgi, scope=scope)

    async def asgi(self, receive: Receive, send: Send, scope: Scope) -> None:
        request = Request(scope, receive=receive)
        auth, user = await self.backend.authenticate(request)
        scope["auth"] = auth
        scope["user"] = user
        inner = self.app(scope)
        await inner(receive, send)

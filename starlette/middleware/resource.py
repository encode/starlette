import functools
import typing

from starlette.types import ASGIApp, ASGIInstance, Message, Receive, Scope, Send


class ResourceMiddleware:
    def __init__(self, app: ASGIApp, name: str) -> None:
        self.app = app
        self.name = name

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope["type"] == "lifespan":
            return ResourceLifespan(self.app, self, scope)
        return functools.partial(self.asgi, scope=scope)

    async def asgi(self, receive: Receive, send: Send, scope: Scope) -> None:
        if "resources" not in scope:
            scope["resources"] = {}
        elif self.name in scope["resources"]:
            raise ValueError(f"Resource {self.name} is already registered")

        resource = await self.get_resource(scope)
        try:
            scope["resources"][self.name] = resource
            inner = self.app(scope)
            await inner(receive, send)
        finally:
            await self.clean_resource(resource)

    async def get_resource(self, scope):  # type: ignore
        raise NotImplementedError()  # pragma: no cover

    async def clean_resource(self, resource: typing.Any) -> None:
        pass  # pragma: no cover

    async def startup(self) -> None:
        pass  # pragma: no cover

    async def shutdown(self) -> None:
        pass  # pragma: no cover


class ResourceLifespan:
    def __init__(
        self, app: ASGIApp, middleware: ResourceMiddleware, scope: Scope
    ) -> None:
        self.inner = app(scope)
        self.middleware = middleware

    async def __call__(self, receive: Receive, send: Send) -> None:
        try:

            async def receiver() -> Message:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await self.middleware.startup()
                elif message["type"] == "lifespan.shutdown":
                    await self.middleware.shutdown()
                return message

            await self.inner(receiver, send)
        finally:
            self.middleware = None  # type: ignore

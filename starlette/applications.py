import typing
import warnings

from starlette.datastructures import State, URLPath
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.middleware.exceptions import ExceptionMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Router
from starlette.types import ASGIApp, Lifespan, Receive, Scope, Send

AppType = typing.TypeVar("AppType", bound="Starlette")


class _ASGIAppProxy:
    """A proxy into an ASGI app that we can re-assign to point to a new
    app without modifying any references to the _ASGIAppProxy itself.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class Starlette:
    """
    Creates an application instance.

    **Parameters:**

    * **debug** - Boolean indicating if debug tracebacks should be returned on errors.
    * **routes** - A list of routes to serve incoming HTTP and WebSocket requests.
    * **middleware** - A list of middleware to run for every request. A starlette
    application will always automatically include two middleware classes.
    `ServerErrorMiddleware` is added as the very outermost middleware, to handle
    any uncaught errors occurring anywhere in the entire stack.
    `ExceptionMiddleware` is added as the very innermost middleware, to deal
    with handled exception cases occurring in the routing or endpoints.
    * **exception_handlers** - A mapping of either integer status codes,
    or exception class types onto callables which handle the exceptions.
    Exception handler callables should be of the form
    `handler(request, exc) -> response` and may be be either standard functions, or
    async functions.
    * **on_startup** - A list of callables to run on application startup.
    Startup handler callables do not take any arguments, and may be be either
    standard functions, or async functions.
    * **on_shutdown** - A list of callables to run on application shutdown.
    Shutdown handler callables do not take any arguments, and may be be either
    standard functions, or async functions.
    * **lifespan** - A lifespan context function, which can be used to perform
    startup and shutdown tasks. This is a newer style that replaces the
    `on_startup` and `on_shutdown` handlers. Use one or the other, not both.
    """

    def __init__(
        self: "AppType",
        debug: bool = False,
        routes: typing.Optional[typing.Sequence[BaseRoute]] = None,
        middleware: typing.Optional[typing.Sequence[Middleware]] = None,
        exception_handlers: typing.Optional[
            typing.Mapping[
                typing.Any,
                typing.Callable[
                    [Request, Exception],
                    typing.Union[Response, typing.Awaitable[Response]],
                ],
            ]
        ] = None,
        on_startup: typing.Optional[typing.Sequence[typing.Callable]] = None,
        on_shutdown: typing.Optional[typing.Sequence[typing.Callable]] = None,
        lifespan: typing.Optional[Lifespan["AppType"]] = None,
    ) -> None:
        # The lifespan context function is a newer style that replaces
        # on_startup / on_shutdown handlers. Use one or the other, not both.
        assert lifespan is None or (
            on_startup is None and on_shutdown is None
        ), "Use either 'lifespan' or 'on_startup'/'on_shutdown', not both."

        self.debug = debug
        self.state = State()
        self.router = Router(
            routes, on_startup=on_startup, on_shutdown=on_shutdown, lifespan=lifespan
        )
        self.exception_handlers = (
            {} if exception_handlers is None else dict(exception_handlers)
        )
        self._pending_exception_handlers = False
        self.user_middleware = [] if middleware is None else list(middleware)
        self._pending_user_middlewares = self.user_middleware.copy()
        # wrap ExceptionMiddleware in a proxy so that
        # we can re-build it when exception handlers get added
        self._exception_middleware = _ASGIAppProxy(
            ExceptionMiddleware(self.router, debug=self.debug)
        )

        self._user_middleware_outer: _ASGIAppProxy | None = None
        self._user_middleware_inner = _ASGIAppProxy(self._exception_middleware.app)
        self.middleware_stack: ASGIApp | None = None

    def build_middleware_stack(self) -> ASGIApp:
        debug = self.debug
        error_handler = None
        exception_handlers: typing.Dict[
            typing.Any, typing.Callable[[Request, Exception], Response]
        ] = {}

        for key, value in self.exception_handlers.items():
            if key in (500, Exception):
                error_handler = value
            else:
                exception_handlers[key] = value

        self._exception_middleware.app = ExceptionMiddleware(
            self.router, handlers=exception_handlers, debug=debug
        )
        self._pending_exception_handlers = False

        user_middleware = self._pending_user_middlewares.copy()
        self._pending_user_middlewares.clear()

        user_middleware_outer: ASGIApp
        if user_middleware:
            # build a new middleware chain that wraps self._exception_middleware
            app: ASGIApp
            app = new_user_middleware_inner = _ASGIAppProxy(self._exception_middleware)
            for cls, options in reversed(user_middleware):
                app = cls(app=app, **options)
            # and set the .app for the previous innermost user middleware to point
            # to this new chain
            self._user_middleware_inner.app = app
            # then replace our innermost user middleware
            self._user_middleware_inner = new_user_middleware_inner

            user_middleware_outer = self._user_middleware_outer or app
        else:
            user_middleware_outer = self._exception_middleware

        return ServerErrorMiddleware(
            app=user_middleware_outer, handler=error_handler, debug=debug
        )

    @property
    def routes(self) -> typing.List[BaseRoute]:
        return self.router.routes

    # TODO: Make `__name` a positional-only argument when we drop Python 3.7 support.
    def url_path_for(self, __name: str, **path_params: typing.Any) -> URLPath:
        return self.router.url_path_for(__name, **path_params)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["app"] = self
        if (
            self.middleware_stack is None
            or self._pending_exception_handlers
            or self._pending_user_middlewares
        ):
            self.middleware_stack = self.build_middleware_stack()
        assert self.middleware_stack is not None
        await self.middleware_stack(scope, receive, send)

    def on_event(self, event_type: str) -> typing.Callable:  # pragma: nocover
        return self.router.on_event(event_type)

    def mount(
        self, path: str, app: ASGIApp, name: typing.Optional[str] = None
    ) -> None:  # pragma: nocover
        self.router.mount(path, app=app, name=name)

    def host(
        self, host: str, app: ASGIApp, name: typing.Optional[str] = None
    ) -> None:  # pragma: no cover
        self.router.host(host, app=app, name=name)

    def add_middleware(self, middleware_class: type, **options: typing.Any) -> None:
        self._pending_user_middlewares.append(Middleware(middleware_class, **options))
        self.user_middleware.insert(0, Middleware(middleware_class, **options))

    def add_exception_handler(
        self,
        exc_class_or_status_code: typing.Union[int, typing.Type[Exception]],
        handler: typing.Callable,
    ) -> None:  # pragma: no cover
        self._pending_exception_handlers = True
        self.exception_handlers[exc_class_or_status_code] = handler

    def add_event_handler(
        self, event_type: str, func: typing.Callable
    ) -> None:  # pragma: no cover
        self.router.add_event_handler(event_type, func)

    def add_route(
        self,
        path: str,
        route: typing.Callable,
        methods: typing.Optional[typing.List[str]] = None,
        name: typing.Optional[str] = None,
        include_in_schema: bool = True,
    ) -> None:  # pragma: no cover
        self.router.add_route(
            path, route, methods=methods, name=name, include_in_schema=include_in_schema
        )

    def add_websocket_route(
        self, path: str, route: typing.Callable, name: typing.Optional[str] = None
    ) -> None:  # pragma: no cover
        self.router.add_websocket_route(path, route, name=name)

    def exception_handler(
        self, exc_class_or_status_code: typing.Union[int, typing.Type[Exception]]
    ) -> typing.Callable:
        warnings.warn(
            "The `exception_handler` decorator is deprecated, and will be removed in version 1.0.0. "  # noqa: E501
            "Refer to https://www.starlette.io/exceptions/ for the recommended approach.",  # noqa: E501
            DeprecationWarning,
        )

        def decorator(func: typing.Callable) -> typing.Callable:
            self.add_exception_handler(exc_class_or_status_code, func)
            return func

        return decorator

    def route(
        self,
        path: str,
        methods: typing.Optional[typing.List[str]] = None,
        name: typing.Optional[str] = None,
        include_in_schema: bool = True,
    ) -> typing.Callable:
        """
        We no longer document this decorator style API, and its usage is discouraged.
        Instead you should use the following approach:

        >>> routes = [Route(path, endpoint=...), ...]
        >>> app = Starlette(routes=routes)
        """
        warnings.warn(
            "The `route` decorator is deprecated, and will be removed in version 1.0.0. "  # noqa: E501
            "Refer to https://www.starlette.io/routing/ for the recommended approach.",  # noqa: E501
            DeprecationWarning,
        )

        def decorator(func: typing.Callable) -> typing.Callable:
            self.router.add_route(
                path,
                func,
                methods=methods,
                name=name,
                include_in_schema=include_in_schema,
            )
            return func

        return decorator

    def websocket_route(
        self, path: str, name: typing.Optional[str] = None
    ) -> typing.Callable:
        """
        We no longer document this decorator style API, and its usage is discouraged.
        Instead you should use the following approach:

        >>> routes = [WebSocketRoute(path, endpoint=...), ...]
        >>> app = Starlette(routes=routes)
        """
        warnings.warn(
            "The `websocket_route` decorator is deprecated, and will be removed in version 1.0.0. "  # noqa: E501
            "Refer to https://www.starlette.io/routing/#websocket-routing for the recommended approach.",  # noqa: E501
            DeprecationWarning,
        )

        def decorator(func: typing.Callable) -> typing.Callable:
            self.router.add_websocket_route(path, func, name=name)
            return func

        return decorator

    def middleware(self, middleware_type: str) -> typing.Callable:
        """
        We no longer document this decorator style API, and its usage is discouraged.
        Instead you should use the following approach:

        >>> middleware = [Middleware(...), ...]
        >>> app = Starlette(middleware=middleware)
        """
        warnings.warn(
            "The `middleware` decorator is deprecated, and will be removed in version 1.0.0. "  # noqa: E501
            "Refer to https://www.starlette.io/middleware/#using-middleware for recommended approach.",  # noqa: E501
            DeprecationWarning,
        )
        assert (
            middleware_type == "http"
        ), 'Currently only middleware("http") is supported.'

        def decorator(func: typing.Callable) -> typing.Callable:
            self.add_middleware(BaseHTTPMiddleware, dispatch=func)
            return func

        return decorator

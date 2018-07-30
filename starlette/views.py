import typing
from functools import update_wrapper
from starlette.decorators import make_asgi


class View:
    def dispatch(self, scope):
        request_method = scope["method"] if scope["method"] != "HEAD" else "GET"
        func = getattr(self, request_method.lower(), None)
        if func is None:
            raise Exception(
                f"Method {request_method} is not implemented for this view."
            )
        return make_asgi(func)(scope)

    @classmethod
    def as_view(cls) -> typing.Callable:
        def view(scope):
            self = cls()
            return self.dispatch(scope)

        view.view_class = cls
        update_wrapper(view, cls, updated=())
        update_wrapper(view, cls.dispatch, assigned=())

        return view

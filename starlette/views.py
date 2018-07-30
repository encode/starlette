import typing
from functools import update_wrapper
from starlette.decorators import make_asgi


class View:
    def dispatch(self, request):
        request_method = request.method if request.method != "HEAD" else "GET"
        func = getattr(self, request_method.lower(), None)
        if func is None:
            raise Exception(
                f"Method {request_method} is not implemented for this view."
            )
        return func(request)

    @classmethod
    def as_view(cls) -> typing.Callable:
        def view(scope):
            self = cls()
            return make_asgi(self.dispatch)(scope)

        view.view_class = cls
        update_wrapper(view, cls, updated=())
        update_wrapper(view, cls.dispatch, assigned=())

        return view

from typing import Any, Callable, Iterator

from typing_extensions import Concatenate, ParamSpec

from starlette.types import ASGIApp

P = ParamSpec("P")


class Middleware:
    def __init__(
        self,
        cls: Callable[Concatenate[ASGIApp, P], Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        self.cls = cls
        self.args = args
        self.kwargs = kwargs

    def __iter__(self) -> Iterator[Any]:
        as_tuple = (self.cls, self.args, self.kwargs)
        return iter(as_tuple)

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        args_strings = [f"{value!r}" for value in self.args]
        option_strings = [f"{key}={value!r}" for key, value in self.kwargs.items()]
        args_repr = ", ".join([self.cls.__name__] + args_strings + option_strings)
        return f"{class_name}({args_repr})"

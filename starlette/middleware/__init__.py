import sys
from typing import Any, Callable, Iterator

from starlette.types import ASGIApp

if sys.version_info >= (3, 10):  # pragma: no cover
    from typing import Concatenate, ParamSpec
else:  # pragma: no cover
    from typing_extensions import Concatenate, ParamSpec


P = ParamSpec("P")


class Middleware:
    def __init__(
        self,
        cls: Callable[Concatenate[ASGIApp, P], Any],
        *args: P.args,
        **options: P.kwargs,
    ) -> None:
        self.cls = cls
        self.options = options

    def __iter__(self) -> Iterator[Any]:
        as_tuple = (self.cls, self.options)
        return iter(as_tuple)

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        option_strings = [f"{key}={value!r}" for key, value in self.options.items()]
        args_repr = ", ".join([self.cls.__name__] + option_strings)
        return f"{class_name}({args_repr})"

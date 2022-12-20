import typing

from starlette.types import ASGIApp


class Middleware:
    def __init__(self, cls: typing.Type[ASGIApp], **options: typing.Any) -> None:
        self.cls = cls
        self.options = options

    def __iter__(self) -> typing.Iterator:
        as_tuple = (self.cls, self.options)
        return iter(as_tuple)

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        option_strings = [f"{key}={value!r}" for key, value in self.options.items()]
        args_repr = ", ".join([self.cls.__name__] + option_strings)
        return f"{class_name}({args_repr})"

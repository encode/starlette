try:
    from functools import cached_property  # type: ignore
except ImportError:  # pragma: no cover
    import typing

    class cached_property:  # type: ignore
        def __init__(
            self, func: typing.Callable, attrname: typing.Optional[str] = None
        ) -> None:
            self.func = func
            self.attrname = attrname
            self.__doc__ = func.__doc__

        def __set_name__(self, owner: typing.Any, name: str) -> None:
            if self.attrname is None:
                self.attrname = name

            elif name != self.attrname:
                raise TypeError(
                    "Cannot assign the same cached_property to two different names "
                    f"({self.attrname!r} and {name!r})."
                )

        def __get__(self, instance: typing.Any, owner: typing.Any = None) -> typing.Any:
            if instance is None:
                return self

            if self.attrname is None:
                raise TypeError(
                    "Cannot use cached_property instance without calling __set_name__ on it."
                )

            try:
                instance.__dict__
            except AttributeError:
                raise TypeError(
                    f"No '__dict__' attribute on {type(instance).__name__!r}"
                ) from None

            value = self.func(instance)
            instance.__dict__[self.attrname] = value

            return value

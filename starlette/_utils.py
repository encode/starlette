import asyncio
import functools
import typing


def is_async_callable(obj: typing.Any) -> bool:
    while isinstance(obj, functools.partial):
        obj = obj.func

    return asyncio.iscoroutinefunction(obj) or (
        callable(obj) and asyncio.iscoroutinefunction(obj.__call__)
    )


def get_or_create_extension(
    scope: typing.MutableMapping[str, typing.Any]
) -> typing.MutableMapping[str, typing.Any]:
    scope["extensions"] = extensions = scope.get("extensions", None) or {}
    extension = extensions["starlette"] = extensions.get("starlette", None) or {}
    return extension

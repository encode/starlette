import typing

from starlette.types import Scope


def get_extension_from_scope(scope: Scope) -> typing.Dict[str, typing.Any]:
    extensions = scope["extensions"] = scope.get("extensions", None) or {}
    extension = extensions["starlette"] = (
        scope["extensions"].get("starlette", None) or {}
    )
    return extension


def get_from_extension(scope: Scope, key: str, default: typing.Any) -> typing.Any:
    starlette_extension_scope = get_extension_from_scope(scope)
    if key in starlette_extension_scope:
        return starlette_extension_scope[key]
    return default

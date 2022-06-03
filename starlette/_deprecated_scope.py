from typing import Any, Dict, Mapping, Set
from warnings import warn


class DeprecatedScope(Dict[str, Any]):
    _deprecated_scope_keys: Set[str] = {
        "app",
        "session",
        "auth",
        "user",
        "state",
        "endpoint",
        "path_params",
        "app_root_path",
        "router",
    }

    def __init__(self, scope: Mapping[str, Any]) -> None:
        super().__init__(scope)
        self["extensions"] = extensions = self.get("extensions", None) or {}
        extensions["starlette"] = self.extension = (
            extensions.get("starlette", None) or {}
        )

    def __getitem__(self, __k: str) -> Any:
        if __k in self._deprecated_scope_keys:
            msg = (
                f'scope["{__k}"] is deprecated, use '
                f'scope["extensions"]["starlette"]["{__k}"] instead'
            )
            warn(msg, DeprecationWarning)
            return self.extension[__k]
        return super().__getitem__(__k)

    def __setitem__(self, __k: str, __v: Any) -> None:
        if __k in self._deprecated_scope_keys:
            self.extension[__k] = __v
        return super().__setitem__(__k, __v)

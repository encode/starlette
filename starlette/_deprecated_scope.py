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

    def __getitem__(self, __k: str) -> Any:
        if __k in self._deprecated_scope_keys:
            msg = (
                f'scope["{__k}"] is deprecated, use '
                f'scope["extensions"]["starlette"]["{__k}"] instead'
            )
            warn(msg, DeprecationWarning)
        return super().__getitem__(__k)

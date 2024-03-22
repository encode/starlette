from __future__ import annotations

import json
from typing import Any, Dict


class JSONParser:
    def __init__(self, options: Dict[str, Any] | None = None) -> None:
        self.options: Dict[str, Any] = options or {}

    @staticmethod
    def loads(stream: bytes, options: Dict[str, Any]) -> Any:
        return json.loads(stream, **options)

    def parse(self, stream: bytes) -> Any:
        return self.loads(stream, self.options)


class JSONSerializer:
    def __init__(self, options: Dict[str, Any] | None = None) -> None:
        self.options: Dict[str, Any] = options or {}

    @staticmethod
    def dumps(data: Any, options: Dict[str, Any]) -> str:
        return json.dumps(data, **options)

    def serialize(self, data: Any) -> bytes:
        return self.dumps(data, self.options).encode("utf-8")

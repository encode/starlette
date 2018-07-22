import typing
import json


def encode_json(content: typing.Any, **kwargs) -> bytes:
    options = {
        "ensure_ascii": False,
        "allow_nan": False,
        "indent": None,
        "separators": (",", ":"),
    }  # type: typing.Dict[str, typing.Any]

    options.update(kwargs)

    return json.dumps(content, **options).encode("utf-8")

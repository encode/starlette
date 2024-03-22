from unittest.mock import Mock

from starlette.json import JSONParser, JSONSerializer


def test_json_serializer_default() -> None:
    serializer = JSONSerializer()
    assert serializer.serialize({"foo": "bar"}) == b'{"foo": "bar"}'
    assert serializer.dumps({"foo": "bar"}, {}) == '{"foo": "bar"}'


def test_json_parser_default() -> None:
    parser = JSONParser()
    assert parser.parse(b'{"foo": "bar"}') == {"foo": "bar"}
    assert parser.loads(b'{"foo": "bar"}', {}) == {"foo": "bar"}


def test_json_serializer_custom() -> None:
    expected_result = "string to encode"

    class CustomSerializer(JSONSerializer):
        dumps = Mock(return_value=expected_result)

    serializer = CustomSerializer()
    assert serializer.serialize({"foo": "bar"}) == expected_result.encode("utf-8")
    serializer.dumps.assert_called_once_with({"foo": "bar"}, {})


def test_json_parser_custom() -> None:
    expected_result = object()

    class CustomParser(JSONParser):
        loads = Mock(return_value=expected_result)

    serializer = CustomParser()
    assert serializer.parse(b'{"foo": "bar"}') is expected_result
    serializer.loads.assert_called_once_with(b'{"foo": "bar"}', {})

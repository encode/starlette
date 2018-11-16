import typing


class Convertor:
    regex = ""

    def convert(self, value: str) -> typing.Any:
        raise NotImplementedError()  # pragma: no cover


class StringConvertor(Convertor):
    regex = "[^/]+"

    def convert(self, value: str) -> typing.Any:
        return value


class PathConvertor(Convertor):
    regex = ".*"

    def convert(self, value: str) -> typing.Any:
        return value


class IntegerConvertor(Convertor):
    regex = "[0-9]+"

    def convert(self, value: str) -> typing.Any:
        return int(value)


class FloatConvertor(Convertor):
    regex = "[0-9]+(.[0-9]+)?"

    def convert(self, value: str) -> typing.Any:
        return float(value)


CONVERTOR_TYPES = {
    "str": StringConvertor(),
    "path": PathConvertor(),
    "int": IntegerConvertor(),
    "float": FloatConvertor(),
}

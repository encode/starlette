import typing


class ValidationError(Exception):
    pass


class Converter:
    def convert(self, value: str) -> typing.Any:
        raise NotImplementedError()  # pragma: no cover


class IntConverter(Converter):
    def convert(self, value: str) -> int:
        try:
            converted_value = int(value)
        except ValueError:
            raise ValidationError(
                "'%s' failed to convert '%s'" % (self.__class__.__name__, value)
            )
        return converted_value


class FloatConverter(Converter):
    def convert(self, value: str) -> float:
        try:
            converted_value = float(value)
        except ValueError:
            raise ValidationError(
                "'%s' failed to convert '%s'" % (self.__class__.__name__, value)
            )
        return converted_value

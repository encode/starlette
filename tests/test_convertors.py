import typing

from starlette.convertors import Convertor, register_url_convertor
from starlette.responses import JSONResponse
from starlette.routing import Router


class DateTimeConvertor(Convertor):
    regex = "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(.[0-9]+)?"

    def convert(self, value: str) -> typing.Any:
        return str(value)

    def to_string(self, value: typing.Any) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%S")


register_url_convertor("datetime", DateTimeConvertor())


class DateConvertor(Convertor):
    regex = "[0-9]{4}-[0-9]{2}-[0-9]{2}"

    def convert(self, value: str) -> typing.Any:
        return str(value)

    def to_string(self, value: typing.Any) -> str:
        return value.strftime("%Y-%m-%d")


register_url_convertor("date", DateConvertor())


class TimeConvertor(Convertor):
    regex = "[0-9]{2}:[0-9]{2}:[0-9]{2}(.[0-9]+)?"

    def convert(self, value: str) -> typing.Any:
        return str(value)

    def to_string(self, value: typing.Any) -> str:
        return value.strftime("%H:%M:%S")


register_url_convertor("time", TimeConvertor())

app = Router()


@app.route("/datetime/{param:datetime}", name="datetime-convertor")
def datetime_convertor(request):
    dt = request.path_params["param"]
    return JSONResponse({"datetime": dt})


@app.route("/date/{param:date}", name="date-convertor")
def date_convertor(request):
    date = request.path_params["param"]
    return JSONResponse({"date": date})


@app.route("/time/{param:time}", name="time-convertor")
def time_convertor(request):
    time = request.path_params["param"]
    return JSONResponse({"time": time})


def test_datetime_convertor(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/datetime/2020-01-01T00:00:00")
    assert response.json() == {"datetime": "2020-01-01T00:00:00"}


def test_date_convertor(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/date/2020-01-01")
    assert response.json() == {"date": "2020-01-01"}


def test_time_convertor(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/time/00:00:00")
    assert response.json() == {"time": "00:00:00"}

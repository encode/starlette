import datetime as dt

from starlette.convertors import Convertor, register_url_convertor
from starlette.responses import JSONResponse
from starlette.routing import Router


class DateTimeConvertor(Convertor):
    regex = "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(.[0-9]+)?"

    def convert(self, value: str) -> dt.datetime:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")

    def to_string(self, value: dt.datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%S")


register_url_convertor("datetime", DateTimeConvertor())


class DateConvertor(Convertor):
    regex = "[0-9]{4}-[0-9]{2}-[0-9]{2}"

    def convert(self, value: str) -> dt.date:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()

    def to_string(self, value: dt.datetime) -> str:
        return value.strftime("%Y-%m-%d")


register_url_convertor("date", DateConvertor())


class TimeConvertor(Convertor):
    regex = "[0-9]{2}:[0-9]{2}:[0-9]{2}(.[0-9]+)?"

    def convert(self, value: str) -> dt.time:
        return dt.datetime.strptime(value, "%H:%M:%S").time()

    def to_string(self, value: dt.datetime) -> str:
        return value.strftime("%H:%M:%S")


register_url_convertor("time", TimeConvertor())

app = Router()


@app.route("/datetime/{param:datetime}", name="datetime-convertor")
def datetime_convertor(request):
    param = request.path_params["param"]
    assert isinstance(param, dt.datetime)
    return JSONResponse({"datetime": param.strftime("%Y-%m-%dT%H:%M:%S")})


@app.route("/date/{param:date}", name="date-convertor")
def date_convertor(request):
    param = request.path_params["param"]
    assert isinstance(param, dt.date)
    return JSONResponse({"date": param.strftime("%Y-%m-%d")})


@app.route("/time/{param:time}", name="time-convertor")
def time_convertor(request):
    param = request.path_params["param"]
    assert isinstance(param, dt.time)
    return JSONResponse({"time": param.strftime("%H:%M:%S")})


def test_datetime_convertor(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/datetime/2020-01-01T00:00:00")
    assert response.json() == {"datetime": "2020-01-01T00:00:00"}

    assert (
        app.url_path_for("datetime-convertor", param=dt.datetime(1996, 1, 22, 23, 0, 0))
        == "/datetime/1996-01-22T23:00:00"
    )


def test_date_convertor(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/date/2020-01-01")
    assert response.json() == {"date": "2020-01-01"}

    assert (
        app.url_path_for("date-convertor", param=dt.date(1996, 1, 22))
        == "/date/1996-01-22"
    )


def test_time_convertor(test_client_factory):
    client = test_client_factory(app)
    response = client.get("/time/00:00:00")
    assert response.json() == {"time": "00:00:00"}

    assert (
        app.url_path_for("time-convertor", param=dt.time(23, 0, 0)) == "/time/23:00:00"
    )

import re
import time

from starlette.applications import Starlette
from starlette.middleware.servertiming import ServerTiming, Ticker, discard_all_tickers, get_tickers, ticker_wrapper
from starlette.responses import PlainTextResponse


def test_server_timing_disabled_response(test_client_factory):
    """
    This feature will be disabled by default
    even if it was explicitly added for security reasons

    """
    app = Starlette(debug=False)

    app.add_middleware(ServerTiming)

    @app.route("/")
    def homepage(request):
        time.sleep(0.3)
        return PlainTextResponse("OK", status_code=200)

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Server-Timing" not in response.headers


def test_server_timing_enabled_response(test_client_factory):
    app = Starlette(debug=True)

    app.add_middleware(ServerTiming)

    @app.route("/")
    def homepage(request):
        time.sleep(0.3)
        return PlainTextResponse("OK", status_code=200)

    client = test_client_factory(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Server-Timing" in response.headers
    assert isinstance(response.headers['Server-Timing'], str)
    assert re.match('app;desc="main app";dur=(.*)?', response.headers["Server-Timing"])

    discard_all_tickers()


def test_ticker():
    ticker = Ticker()

    def test_function():
        ticker.start()
        time.sleep(0.007)
        ticker.end()

    test_function()

    assert ticker.duration == 7
    discard_all_tickers()


def test_multiple_tickers():
    def sub_function():
        ticker = Ticker()
        ticker.start()
        time.sleep(0.007)
        ticker.end()

    def nested_function():
        ticker = Ticker()
        ticker.start()
        time.sleep(0.014)
        ticker.end()

    def main_function():
        ticker = Ticker()
        ticker.start()
        time.sleep(0.021)
        ticker.end()
        nested_function()

    main_function()
    sub_function()

    list_tickers = get_tickers()

    total_ticker_duration = [ticker.duration for ticker in list_tickers]
    assert len(list_tickers) == 3
    assert sum(total_ticker_duration) == 42
    discard_all_tickers()


def test_ticker_wrapper():

    @ticker_wrapper
    def test_function():
        time.sleep(0.012)

    test_function()

    list_tickers = get_tickers()

    test_function_ticker = list_tickers[0]

    total_ticker_duration = [ticker.duration for ticker in list_tickers]
    assert sum(total_ticker_duration) == 12
    assert len(list_tickers) == 1
    assert test_function_ticker.name == 'test_function'

    discard_all_tickers()


def test_ticker_attributes():
    ticker = Ticker("sql", "fetching data to database")
    assert ticker.name is "sql"
    assert ticker.description is "fetching data to database"

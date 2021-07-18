from starlette.types import ASGIApp
import typing
import threading
import time

from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

_thread_local = threading.local()

class Ticker():
    def __init__(self, name='app', description='main app'):
        self.name = name
        self.description = description
        self._start = self._end = None

    def start(self):
        self._start = time.time()
        _add_ticker(self)

    def end(self):
        self._end = time.time()

    @property
    def duration(self):
        if self._start:
            return int(((self._end or time.time()) - self._start) * 1000)
        else:
            return 0


def get_tickers() -> typing.List[Ticker]:
    return _thread_local.__dict__.setdefault("tickers", [])


def discard_all_tickers() -> typing.List[Ticker]:
    _thread_local.__dict__["tickers"] = []


def _add_ticker(ticker) -> None:
    get_tickers().append(ticker)


def ticker_wrapper(func: typing.Callable):
    def wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:

        ticker = Ticker(func.__name__)
        ticker.start()

        data = func(*args, **kwargs)
        ticker.end()

        return data
    return wrapper


class ServerTiming(BaseHTTPMiddleware):
    """
    Adds Server-Timing to every HTTP requests
    """

    def __init__(self, app: ASGIApp, allow_origins: typing.Sequence[str] = ()) -> None:
        self._allow_origins = allow_origins
        super().__init__(app, dispatch=self.dispatch)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):

        defaultTimer = Ticker()
        defaultTimer.start()

        response = await call_next(request)

        defaultTimer.end()

        header = self.build_server_timing_header()

        if (header is not None) and self.app.debug:
            response.headers['Server-Timing'] = header
            response.headers['Timing-Allow-Origin'] = self.build_allowed_origin()

        return response

    def build_allowed_origin(self):
        if '*' in self._allow_origins or len(self._allow_origins) == 0:
            return '*'
        elif self._allow_origins:
            return ", ".join(self._allow_origins)

    def build_server_timing_header(self):
        tickers = [
            ticker.name + ';desc="' + ticker.description
            + '";dur=' + str(ticker.duration)
            for ticker in get_tickers()
        ]

        if tickers:
            header = ','.join(tickers)
            discard_all_tickers()
            return header

        return None

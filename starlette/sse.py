import asyncio
import contextlib
import enum
import io
import re
from typing import Any, Optional, Generator

from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse


class SseState(enum.Enum):
    CONNECTING = 0
    OPENED = 1
    CLOSED = 2


# Legacy proxy servers are known to, in certain cases, drop HTTP connections after a short timeout.
# To protect against such proxy servers, authors can include a comment line (one starting with a ':' character) every 15 seconds or so.
class ServerSentEvent:
    def __init__(
            self,
            data: str,
            *,
            event: Optional[str] = None,
            id: Optional[int] = None,
            retry: Optional[int] = None,
    ) -> None:
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

        self.DEFAULT_SEPARATOR = "\r\n"
        self.LINE_SEP_EXPR = re.compile(r"\r\n|\r|\n")
        self._sep = self.DEFAULT_SEPARATOR

    def encode(self) -> bytes:
        """Send data using EventSource protocol

        :param str data: The data field for the message.
        :param str id: The event ID to set the EventSource object's last
            event ID value to.
        :param str event: The event's type. If this is specified, an event will
            be dispatched on the browser to the listener for the specified
            event name; the web site would use addEventListener() to listen
            for named events. The default event type is "message".
        :param int retry: The reconnection time to use when attempting to send
            the event. [What code handles this?] This must be an integer,
            specifying the reconnection time in milliseconds. If a non-integer
            value is specified, the field is ignored.
        """
        buffer = io.StringIO()
        if self.id is not None:
            buffer.write(self.LINE_SEP_EXPR.sub("", f"id: {self.id}"))
            buffer.write(self._sep)
        if self.event is not None:
            buffer.write(self.LINE_SEP_EXPR.sub("", f"event: {self.event}"))
            buffer.write(self._sep)
        for chunk in self.LINE_SEP_EXPR.split(self.data):
            buffer.write(f"data: {chunk}")
            buffer.write(self._sep)
        if self.retry is not None:
            if not isinstance(self.retry, int):
                raise TypeError("retry argument must be int")
            buffer.write(f"retry: {self.retry}")
            buffer.write(self._sep)
        buffer.write(self._sep)
        return buffer.getvalue().encode("utf-8")


class EventSourceResponse(StreamingResponse):

    DEFAULT_PING_INTERVAL = 15

    def __init__(
            self,
            content: Generator[ServerSentEvent, None, None],
            status_code: int = 200,
            headers: dict = None,
            background: BackgroundTask = None,
            sep: str = None
    ) -> None:

        # assert scope["type"] == "http"
        _headers = dict()
        if headers is not None:
            _headers.update(headers)

        # mandatory for servers-sent events headers
        _headers['Content-Type'] = 'text/event-stream'
        _headers['Cache-Control'] = 'no-cache'
        _headers['Connection'] = 'keep-alive'
        _headers['X-Accel-Buffering'] = 'no'
        _headers['Transfer-Encoding'] = 'chunked'

        super(EventSourceResponse, self).__init__(
            content=content,
            status_code=status_code,
            headers=_headers,
            media_type="text/html",
            background=background
        )

        self._loop = None
        self._ping_interval = self.DEFAULT_PING_INTERVAL
        self._ping_task = None

        self._loop = asyncio.get_event_loop()
        self._ping_task = self._loop.create_task(self._ping())
        _ = None

    async def wait(self):
        """EventSourceResponse object is used for streaming data to the client,
        this method returns future, so we can wain until connection will
        be closed or other task explicitly call ``stop_streaming`` method.
        """
        if self._ping_task is None:
            raise RuntimeError('Response is not started')
        with contextlib.suppress(asyncio.CancelledError):
            await self._ping_task

    def stop_streaming(self):
        """Used in conjunction with ``wait`` could be called from other task
        to notify client that server no longer wants to stream anything.
        """
        if self._ping_task is None:
            raise RuntimeError('Response is not started')
        self._ping_task.cancel()

    def enable_compression(self, force=False):
        raise NotImplementedError

    @property
    def ping_interval(self):
        """Time interval between two ping massages"""
        return self._ping_interval

    @ping_interval.setter
    def ping_interval(self, value):
        """Setter for ping_interval property.

        :param int value: interval in sec between two ping values.
        """

        if not isinstance(value, int):
            raise TypeError("ping interval must be int")
        if value < 0:
            raise ValueError("ping interval must be greater then 0")

        self._ping_interval = value

    async def _ping(self):
        # periodically send ping to the browser. Any message that
        # starts with ":" colon ignored by a browser and could be used
        # as ping message.
        while True:
            await asyncio.sleep(self._ping_interval, loop=self._loop)
            await self.write(': ping{0}{0}'.format(self._sep).encode('utf-8'))  # TODO: Fix

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.stop_streaming()
        await self.wait()
        return

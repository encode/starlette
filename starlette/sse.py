import asyncio
import contextlib
import enum
import inspect
import io
import logging
import re
from datetime import datetime
from typing import Any, Optional, Generator, Union, Dict, AsyncGenerator

from aiostream import stream

from starlette.background import BackgroundTask
from starlette.concurrency import iterate_in_threadpool
from starlette.responses import Response
from starlette.types import Scope, Receive, Send

_log = logging.getLogger(__name__)


class SseState(enum.Enum):
    CONNECTING = 0
    OPENED = 1
    CLOSED = 2


class ServerSentEvent:
    def __init__(
            self,
            data: Any,
            *,
            event: Optional[str] = None,
            id: Optional[int] = None,
            retry: Optional[int] = None,
            sep: str = None
    ) -> None:
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

        self.DEFAULT_SEPARATOR = "\r\n"
        self.LINE_SEP_EXPR = re.compile(r"\r\n|\r|\n")
        self._sep = sep if sep is not None else self.DEFAULT_SEPARATOR

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

        for chunk in self.LINE_SEP_EXPR.split(str(self.data)):
            buffer.write(f"data: {chunk}")
            buffer.write(self._sep)

        if self.retry is not None:
            if not isinstance(self.retry, int):
                raise TypeError("retry argument must be int")
            buffer.write(f"retry: {self.retry}")
            buffer.write(self._sep)

        buffer.write(self._sep)
        return buffer.getvalue().encode("utf-8")


class EventSourceResponse(Response):
    """ Implements the ServerSentEvent Protocol: https://www.w3.org/TR/2009/WD-eventsource-20090421/

        Responses must not be compressed by middleware in order to work properly.
    """

    def __init__(
            self,
            content: Union[
                Generator[Union[str, Dict], None, None],
                AsyncGenerator[Union[str, Dict], None]
            ],
            status_code: int = 200,
            headers: dict = None,
            media_type: str = "text/html",
            background: BackgroundTask = None,
            ping: float = 15,
            sep: str = None
    ) -> None:
        self.sep = sep
        if inspect.isasyncgen(content):
            self.body_iterator = content
        else:
            self.body_iterator = iterate_in_threadpool(content)
        self.status_code = status_code
        self.media_type = self.media_type if media_type is None else media_type
        self.background = background

        _headers = dict()
        if headers is not None:
            _headers.update(headers)

        # mandatory for servers-sent events headers
        _headers['Content-Type'] = 'text/event-stream'
        _headers['Cache-Control'] = 'no-cache'
        _headers['Connection'] = 'keep-alive'
        _headers['X-Accel-Buffering'] = 'no'
        # _headers['Transfer-Encoding'] = 'chunked'

        self.init_headers(_headers)

        self._loop = None
        self._ping_interval = ping
        self._ping_task = None
        self.active = True

        self._loop = asyncio.get_event_loop()
        self._ping_task = None

        # self.combined_streams = stream.merge(self.body_iterator, self._ping())
        self.combined_streams = stream.merge(self.body_iterator)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )

        self._ping_task = self._loop.create_task(self._ping(send))

        async with self.combined_streams.stream() as streamer:
            async for data in streamer:
                if isinstance(data, dict):
                    chunk = ServerSentEvent(**data, sep=self.sep).encode()
                else:
                    chunk = ServerSentEvent(str(data), sep=self.sep).encode()
                _log.debug(f"chunk: {chunk}")
                # if not isinstance(chunk, bytes):
                #     chunk = chunk.encode(self.charset)
                await send({"type": "http.response.body", "body": chunk, "more_body": True})

        self.stop_streaming()
        await self.wait()
        _log.debug(f"streaming stopped.")
        await send({"type": "http.response.body", "body": b"", "more_body": False})

        if self.background is not None:
            await self.background()

    async def wait(self):
        """EventSourceResponse object is used for streaming data to the client,
        this method returns future, so we can wain until connection will
        be closed or other task explicitly call ``stop_streaming`` method.
        """
        if self._ping_task is None:
            raise RuntimeError('Response is not started')
        with contextlib.suppress(asyncio.CancelledError):
            await self._ping_task
            _log.debug(f"SSE ping stopped.")

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

        if not isinstance(value, float):
            raise TypeError("ping interval must be float")
        if value < 0:
            raise ValueError("ping interval must be greater then 0")

        self._ping_interval = value

    async def _ping(self, send: Send):
        # Legacy proxy servers are known to, in certain cases, drop HTTP connections after a short timeout.
        # To protect against such proxy servers, authors can include a comment line
        # (one starting with a ':' character) every 15 seconds or so.
        while self.active:
            await asyncio.sleep(self._ping_interval, loop=self._loop)
            ping = ServerSentEvent(f": ping {datetime.utcnow()}").encode()
            _log.debug(f"ping: {ping}")
            await send({"type": "http.response.body", "body": ping, "more_body": True})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.stop_streaming()
        await self.wait()
        return

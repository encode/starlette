import asyncio
import contextlib
import io
import re

from aiohttp.web import HTTPMethodNotAllowed, StreamResponse

from .helpers import _ContextManager

__version__ = '2.2.0'
__all__ = ['EventSourceResponse', 'sse_response']


class EventSourceResponse(StreamResponse):
    """This object could be used as regular aiohttp response for
    streaming data to client, usually browser with EventSource::

        async def hello(request):
            # create response object
            resp = await EventSourceResponse()
            async with resp:
                # stream data
                resp.send('foo')
            return resp
    """

    DEFAULT_PING_INTERVAL = 15
    DEFAULT_SEPARATOR = '\r\n'
    LINE_SEP_EXPR = re.compile(r'\r\n|\r|\n')

    def __init__(self, *, status=200, reason=None, headers=None, sep=None):
        super().__init__(status=status, reason=reason)

        if headers is not None:
            self.headers.extend(headers)

        # mandatory for servers-sent events headers
        self.headers['Content-Type'] = 'text/event-stream'
        self.headers['Cache-Control'] = 'no-cache'
        self.headers['Connection'] = 'keep-alive'
        self.headers['X-Accel-Buffering'] = 'no'

        self._loop = None
        self._ping_interval = self.DEFAULT_PING_INTERVAL
        self._ping_task = None
        self._sep = sep if sep is not None else self.DEFAULT_SEPARATOR

    async def _prepare(self, request):
        await self.prepare(request)
        return self

    async def prepare(self, request):
        """Prepare for streaming and send HTTP headers.

        :param request: regular aiohttp.web.Request.
        """
        if request.method != 'GET':
            raise HTTPMethodNotAllowed(request.method, ['GET'])

        if not self.prepared:
            writer = await super().prepare(request)
            self._loop = request.app.loop
            self._ping_task = self._loop.create_task(self._ping())
            # explicitly enabling chunked encoding, since content length
            # usually not known beforehand.
            self.enable_chunked_encoding()
            return writer
        else:
            # hackish way to check if connection alive
            # should be updated once we have proper API in aiohttp
            # https://github.com/aio-libs/aiohttp/issues/3105
            if request.protocol.transport is None:
                # request disconnected
                raise asyncio.CancelledError()

    async def send(self, data, id=None, event=None, retry=None):
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
        if id is not None:
            buffer.write(self.LINE_SEP_EXPR.sub('', 'id: {}'.format(id)))
            buffer.write(self._sep)

        if event is not None:
            buffer.write(self.LINE_SEP_EXPR.sub('', 'event: {}'.format(event)))
            buffer.write(self._sep)

        for chunk in self.LINE_SEP_EXPR.split(data):
            buffer.write('data: {}'.format(chunk))
            buffer.write(self._sep)

        if retry is not None:
            if not isinstance(retry, int):
                raise TypeError('retry argument must be int')
            buffer.write('retry: {}'.format(retry))
            buffer.write(self._sep)

        buffer.write(self._sep)
        await self.write(buffer.getvalue().encode('utf-8'))

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
            await self.write(': ping{0}{0}'.format(self._sep).encode('utf-8'))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.stop_streaming()
        await self.wait()
        return


def sse_response(request, *, status=200, reason=None, headers=None, sep=None,
                 response_cls=EventSourceResponse):
    if not issubclass(response_cls, EventSourceResponse):
        raise TypeError(
            'response_cls must be subclass of '
            'aiohttp_sse.EventSourceResponse, got {}'.format(response_cls))

    sse = response_cls(status=status, reason=reason, headers=headers, sep=sep)
    return _ContextManager(sse._prepare(request))

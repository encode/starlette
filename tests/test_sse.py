import asyncio
import logging

import pytest
from aiostream import stream

from starlette.responses import StreamingResponse
from starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.testclient import TestClient

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)


@pytest.mark.parametrize('input,expected', [
    ('integer', b"data: 1\r\n\r\n"),
    ('dict1', b"data: 1\r\n\r\n"),
    ('dict2', b'event: message\r\ndata: 1\r\n\r\n'),
])
def test_sync_event_source_response(input, expected):
    async def app(scope, receive, send):
        async def numbers(minimum, maximum):
            for i in range(minimum, maximum + 1):
                await asyncio.sleep(0.1)
                if input == 'integer':
                    yield i
                elif input == 'dict1':
                    yield dict(data=i)
                elif input == 'dict2':
                    yield dict(data=i, event="message")

        generator = numbers(1, 5)
        response = EventSourceResponse(generator, ping=0.2)
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.content.decode().count('ping') == 2
    assert expected in response.content
    print(response.content)


@pytest.mark.asyncio
async def test_wait_stop_streaming_errors():
    response = EventSourceResponse(0)
    with pytest.raises(RuntimeError) as ctx:
        await response.wait()
    assert str(ctx.value) == 'Response is not started'

    with pytest.raises(RuntimeError) as ctx:
        response.stop_streaming()
    assert str(ctx.value) == 'Response is not started'


def test_compression_not_implemented():
    response = EventSourceResponse(0)
    with pytest.raises(NotImplementedError):
        response.enable_compression()


@pytest.mark.parametrize('input, expected', [
    ("foo", b'data: foo\r\n\r\n'),
    (dict(data="foo", event="bar"), b'event: bar\r\ndata: foo\r\n\r\n'),
    (dict(data="foo", event="bar", id="xyz"), b'id: xyz\r\nevent: bar\r\ndata: foo\r\n\r\n'),
    (dict(data="foo", event="bar", id="xyz", retry=1), b'id: xyz\r\nevent: bar\r\ndata: foo\r\nretry: 1\r\n\r\n'),
])
def test_server_sent_event(input, expected):
    print(input, expected)
    if isinstance(input, str):
        assert ServerSentEvent(input).encode() == expected
    else:
        assert ServerSentEvent(**input).encode() == expected


@pytest.mark.parametrize('stream_sep,line_sep',
                         [('\n', '\n',),
                          ('\n', '\r',),
                          ('\n', '\r\n',),
                          ('\r', '\n',),
                          ('\r', '\r',),
                          ('\r', '\r\n',),
                          ('\r\n', '\n',),
                          ('\r\n', '\r',),
                          ('\r\n', '\r\n',), ],
                         ids=('stream-LF:line-LF',
                              'stream-LF:line-CR',
                              'stream-LF:line-CR+LF',
                              'stream-CR:line-LF',
                              'stream-CR:line-CR',
                              'stream-CR:line-CR+LF',
                              'stream-CR+LF:line-LF',
                              'stream-CR+LF:line-CR',
                              'stream-CR+LF:line-CR+LF',
                              ))
def test_multiline_data(stream_sep, line_sep):
    lines = line_sep.join(['foo', 'bar', 'xyz'])
    result = ServerSentEvent(lines, event="event", sep=stream_sep).encode()
    assert result == "event: event{0}data: foo{0}data: bar{0}data: xyz{0}{0}".format(stream_sep).encode()


@pytest.mark.parametrize('sep',
                         ['\n', '\r', '\r\n'],
                         ids=('LF', 'CR', 'CR+LF'))
def test_custom_sep(sep):
    result = ServerSentEvent('foo', event="event", sep=sep).encode()
    assert result == "event: event{0}data: foo{0}{0}".format(sep).encode()

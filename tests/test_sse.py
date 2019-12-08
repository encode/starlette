from starlette.responses import StreamingResponse
from starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.testclient import TestClient


def test_sync_streaming_response():
    async def app(scope, receive, send):
        def numbers(minimum, maximum):
            for i in range(minimum, maximum + 1):
                yield ServerSentEvent(str(i)).encode()

        generator = numbers(1, 5)
        response = EventSourceResponse(generator)
        await response(scope, receive, send)

    client = TestClient(app)
    response = client.get("/")
    assert response.content == b'data: 1\r\n\r\ndata: 2\r\n\r\ndata: 3\r\n\r\ndata: 4\r\n\r\ndata: 5\r\n\r\n'


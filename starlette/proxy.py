from starlette.request import Request
from starlette.response import StreamingResponse
from urllib.parse import unquote
import asyncio
import aiohttp


class Proxy:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = None
        self.semaphore = asyncio.Semaphore(20)

    def __call__(self, scope):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return _ProxyResponder(scope, self.base_url, self.session, self.semaphore)


async def _stream_response_body(response, chunk_size=4096):
    while True:
        chunk = await response.content.read(chunk_size)
        if not chunk:
            return
        yield chunk


class _ProxyResponder:
    def __init__(self, scope, base_url, session, semaphore):
        self.scope = scope
        self.base_url = base_url
        self.session = session
        self.semaphore = semaphore

    async def __call__(self, receive, send):
        request = Request(self.scope, receive)
        method = request.method
        url = self.base_url + request.relative_url
        headers = request.headers.mutablecopy()
        del headers['host']
        data = request.stream()
        async with self.semaphore:
            response = await self.session.request(method, url, data=data, headers=headers)
            content_iterator = _stream_response_body(response)
            response = StreamingResponse(content_iterator, status_code=response.status, headers=response.headers)
            await response(receive, send)

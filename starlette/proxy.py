from starlette.request import Request
from starlette.response import Response
from urllib.parse import unquote
import asyncio
import aiohttp


class Proxy:
    def __init__(self, base_url, max_concurrency=20):
        self.base_url = base_url
        self.session = None
        self.semaphore = asyncio.Semaphore(max_concurrency)

    def __call__(self, scope):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return _ProxyResponder(scope, self.base_url, self.session, self.semaphore)


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
        del headers["host"]
        headers["connection"] = "keep-alive"
        data = await request.body()
        kwargs = {"method": method, "url": url, "data": data, "headers": headers}
        async with self.semaphore:
            original = await self.session.request(**kwargs)
            body = await original.read()
        response = Response(body, status_code=original.status, headers=original.headers)
        await response(receive, send)

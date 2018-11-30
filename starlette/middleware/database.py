import asyncpgsa
import functools


class DatabaseMiddleware:
    def __init__(self, app, database_url):
        self.app = app
        self.database_url = database_url
        self.pool = None

    def __call__(self, scope):
        if scope['type'] == 'lifespan':
            return DatabaseLifespan(self.app, self, scope)
        return functools.partial(self.asgi, scope=scope)

    async def asgi(self, receive, send, scope=None):
        conn = await self.pool.acquire()
        try:
            scope['db'] = conn
            inner = self.app(scope)
            await inner(receive, send)
        finally:
            await conn.close()

    async def startup(self):
        self.pool = await asyncpgsa.create_pool(self.database_url)

    async def shutdown(self):
        await self.pool.close()


class DatabaseLifespan:
    def __init__(self, app, middleware, scope):
        self.inner = app(scope)
        self.middleware = middleware

    async def __call__(self, receive, send):
        try:
            async def receiver():
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    await self.middleware.startup()
                elif message['type'] == 'lifespan.shutdown':
                    await self.middleware.shutdown()
                return message
            await self.inner(receiver, send)
        finally:
            self.middleware = None

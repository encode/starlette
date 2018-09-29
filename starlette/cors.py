import functools


cors_headers = [
    b"access-control-allow-origin",
    b"access-control-expose-headers",
    b"access-control-allow-credentials",
    b"access-control-allow-headers",
    b"access-control-allow-methods",
    b"access-control-max-age",
]

DEFAULT = {
    "allow_origin": b"*",
    "expose_headers": b"",
    "allow_credentials": b"false",
    "allow_headers": b"*",
    "allow_methods": b"GET, HEAD, POST, OPTIONS, PUT, PATCH, DELETE",
    "max_age": b"86400",
}


class CORSMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, scope):
        return functools.partial(self.handler, scope=scope)

    async def handler(self, receive, send, scope=None):
        sender = functools.partial(self.sender, send=send)
        inner = self.app(scope)
        await inner(receive, sender)

    async def sender(self, message, send=None):
        if message["type"] == "http.response.start":
            headers = message["headers"]
            for header, value in zip(cors_headers, DEFAULT.values()):
                headers.append((header, value))
        await send(message)
import brotli

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BrotliMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 500) -> None:
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            if "br" in headers.get("Accept-Encoding", ""):
                responder = BrotliResponser(self.app, self.minimum_size)
                await responder(scope, receive, send)
                return
        await self.app(scope, receive, send)


class BrotliResponser:
    """
    Implemention of  Brotli compression Algorithm  as Middleware 
    Utility of long responses json response to high level compression on data and reduced time  of transfer.  
    """
    def __init__(self, app: ASGIApp, minimum_size: int):
        self.app = app
        self.minimum_size = minimum_size
        ###
        self.send = unattached_send  # type: Send
        self.initial_message = {}  # type: Message
        self.started = False
        ###
        self.initial_message: Message = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        self.send = send
        await self.app(scope, receive, self.send_with_brotli)

    async def send_with_brotli(self, message: Message):
        message_type = message["type"]
        if message_type == "http.response.start":
            self.initial_message = message
        elif message_type == "http.response.body" and not self.started:
            self.started = True
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            if len(body) < self.minimum_size and not more_body:
                # Don't apply Brotli to the content sent to the response
                await self.send(self.initial_message)
                await self.send(message)
            elif not more_body:
                # Go go Brotli
                # Get body compressed
                body = brotli.compress(body)
                # Add Content-Encoding, Content-Length and Accept-Encoding
                # Why a mutable header?
                headers = MutableHeaders(raw=self.initial_message["headers"])
                headers["Content-Encoding"] = "br"
                headers.add_vary_header("Accept-Encoding")
                headers["Content-Length"] = str(len(body))

                # Body
                message["body"] = body

                await self.send(self.initial_message)
                await self.send(message)
            else:
                # streaming response, I think
                # how it works the streaming response with Brotli
                headers = MutableHeaders(raw=self.initial_message["headers"])
                headers["Content-Encoding"] = "br"
                headers.add_vary_header("Accept-Encoding")
                del headers["Content-Length"]

                # writing body
                body = brotli.compress(body)
                message["body"] = body

                await self.send(self.initial_message)
                await self.send(message)

        elif message_type == "http.response.body":
            # Remaining streaming Brotli response
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            message["body"] = brotli.compress(body)

            await self.send(message)

async def unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover

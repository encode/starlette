import enum
import typing
import json

from starlette.exceptions import WebSocketDisconnect, WebSocketNotConnected, WebSocketProtocolError
from starlette.utils import encode_json


class Status():
    """
    https://tools.ietf.org/html/rfc6455#page-45
    """

    @property
    def WS_1000_OK(self):
        """
        1000 indicates a normal closure, meaning that the purpose for
        which the connection was established has been fulfilled.
        """
        return 1000

    @property
    def WS_1001_LEAVING(self):
        """
        1001 indicates that an endpoint is "going away", such as a server
        going down or a browser having navigated away from a page.
        """
        return 1001

    @property
    def WS_1002_PROT_ERROR(self):
        """
        1002 indicates that an endpoint is terminating the connection due
        to a protocol error.
        """
        return 1002

    @property
    def WS_1003_UNSUPPORTED_TYPE(self):
        """
        1003 indicates that an endpoint is terminating the connection
        because it has received a type of data it cannot accept (e.g., an
        endpoint that understands only text data MAY send this if it
        receives a binary message).
        """
        return 1003

    @property
    def WS_1007_INALID_DATA(self):
        """
        1007 indicates that an endpoint is terminating the connection
        because it has received data within a message that was not
        consistent with the type of the message (e.g., non-UTF-8 [RFC3629]
        data within a text message).
        """
        return 1007

    @property
    def WS_1008_POLICY_VIOLATION(self):
        """
        1008 indicates that an endpoint is terminating the connection
        because it has received a message that violates its policy.  This
        is a generic status code that can be returned when there is no
        other more suitable status code (e.g., 1003 or 1009) or if there
        is a need to hide specific details about the policy.
        """
        return 1008

    @property
    def WS_1009_TOO_BIG(self):
        """
        1009 indicates that an endpoint is terminating the connection
        because it has received a message that is too big for it to
        process.
        """
        return 1009

    @property
    def WS_1010_TLS_FAIL(self):
        """
        1010 indicates that an endpoint (client) is terminating the
        connection because it has expected the server to negotiate one or
        more extension, but the server didn't return them in the response
        message of the WebSocket handshake.  The list of extensions that
        """
        return 1010


status = Status()


class WSState(enum.Enum):
    CONNECTING = 0
    CONNECTED = 1
    CLOSED = 2


class WebSocket(object):
    """
    https://github.com/django/asgiref/blob/master/specs/www.rst
    """
    def __init__(self,
                 request,
                 asgi_receive: typing.Callable,
                 asgi_send: typing.Callable,
                 ) -> None:

        if request.get('type') != 'websocket':
            raise WebSocketProtocolError(detail="Not a websocket scope")

        self.request = request
        self._asgi_send = asgi_send
        self._asgi_receive = asgi_receive
        self._state = WSState.CLOSED

    @property
    def subprotocols(self) -> list:
        return self.request.get('subprotocols', [])

    @property
    def connected(self):
        return self._state == WSState.CONNECTED

    @property
    def connecting(self):
        return self._state == WSState.CONNECTING

    @property
    def closed(self):
        return self._state == WSState.CLOSED

    async def connect(self,
                      subprotocol: str = None,
                      close: bool = False,
                      close_code: int = status.WS_1000_OK) -> None:

        # Accept or Refuse an incoming connection
        if self._state != WSState.CLOSED:
            # Try to send a close and be friendly to the otherside before raising
            await self.close(code=status.WS_1001_LEAVING)

            raise WebSocketProtocolError(
                detail="Attempting to connect a WebSocket that is not closed: %s" % self._state
            )

        # Expecting a connect message
        msg = await self._asgi_receive()

        if msg['type'] != 'websocket.connect':
            raise WebSocketProtocolError(
                'Expected WebSocket `connection` but got: %s' % msg['type']
            )

        self._state = WSState.CONNECTING

        if close:
            await self.close(code=close_code)
            return

        # Try to accept and upgrade the websocket
        await self.accept(subprotocol)

    async def accept(self, subprotocol: str = None) -> None:
        if self._state != WSState.CONNECTING:
            raise WebSocketProtocolError(
                detail="Attempting to accept a WebSocket that is not connecting"
            )

        msg = {'type': 'websocket.accept'}
        if subprotocol:
            msg['subprotocol'] = subprotocol

        await self._asgi_send(msg)
        self._state = WSState.CONNECTED

    async def receive_json(self, loads: typing.Callable = None) -> typing.Union[dict, list]:
        jloads = loads or json.loads
        return jloads(await self.receive())

    async def receive(self) -> typing.Union[str, bytes]:
        if self._state != WSState.CONNECTED:
            raise WebSocketNotConnected()

        msg = await self._asgi_receive()

        if msg['type'] == 'websocket.disconnect':
            self._state = WSState.CLOSED
            raise WebSocketDisconnect(status_code=msg.get('code', status.WS_1000_OK))

        return msg.get('text', msg.get('bytes'))

    async def send_msg(self, msg: dict) -> None:
        if self._state != WSState.CONNECTED:
            raise WebSocketNotConnected()

        try:
            await self._asgi_send(msg)
        except Exception as e:
            self._state = WSState.CLOSED
            raise WebSocketDisconnect(str(e))

    async def send(self, data: typing.Union[str, bytes]) -> None:
        msg = {
            'type': 'websocket.send',
        }

        if data:
            if isinstance(data, bytes):
                msg['bytes'] = data
            else:
                msg['text'] = data

        await self.send_msg(msg)

    async def send_json(self,
                        data: typing.Union[dict, list],
                        dumps: typing.Callable = None) -> None:
        jdumps = dumps or encode_json

        await self.send(jdumps(data))

    async def close(self, code: int = status.WS_1000_OK) -> None:
        if self._state == WSState.CLOSED:
            raise WebSocketNotConnected()

        message = {
            'type': 'websocket.close',
            'code': code,
        }

        await self._asgi_send(message)
        self._state = WSState.CLOSED

    def __repr__(self) -> str:
        return "<WebSocket state:%s>" % (self._state)


#  class WebSocketRequest:
#      def __init__(self,
#                   method: http.Method,
#                   url: http.URL,
#                   headers: http.Headers=None) -> None:
#          self.method = method
#          self.url = url
#          self.headers = http.Headers() if (headers is None) else headers


#  class WebSocketResponse():
#      def __init__(self,
#                   content: typing.Union[str, bytes]=None,
#                   status_code: int=1000,
#                   exc_info=None) -> None:

#          self.content = self.render(content)
#          self.status_code = status_code
#          self.exc_info = exc_info

#      def render(self, content: typing.Any) -> typing.Union[str, bytes, None]:
#          if content is None or isinstance(content, (bytes, str)):
#              return content

#          raise RuntimeError(
#              "%s content must be string or bytes. Got %s." %
#              (self.__class__.__name__, type(content).__name__)
#          )


#  class WebSocketJSONResponse(WebSocketResponse):
#      charset = None
#      options = {
#          'ensure_ascii': False,
#          'allow_nan': False,
#          'indent': None,
#          'separators': (',', ':'),
#      }

#      def render(self, content: typing.Any) -> bytes:
#          return encode_json(content)

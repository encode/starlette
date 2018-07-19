from typing import Union


class ClientDisconnect(Exception):
    pass


class WebSocketException(Exception):
    default_status_code = 1000  # type: int
    default_detail = None

    def __init__(self,
                 detail: Union[str, bytes]=None,
                 status_code: int=None) -> None:

        self.detail = self.default_detail if (detail is None) else detail
        self.status_code = self.default_status_code if (status_code is None) else status_code


class WebSocketDisconnect(WebSocketException):
    default_status_code = 1000
    default_detail = 'WebSocket has been disconnected'


class WebSocketProtocolError(WebSocketException):
    default_detail = 'WebSocket protocol error'
    default_status_code = 1002


class WebSocketNotConnected(WebSocketException):
    default_detail = 'WebSocket is not connected or open'

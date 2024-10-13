from starlette.applications import Starlette
from starlette.exceptions import HTTPException, WebSocketException
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    raise WebSocketException(code=1001)
    raise HTTPException(400)


app = Starlette(routes=[WebSocketRoute("/ws", websocket_endpoint)])

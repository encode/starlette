Enable sessions by using [SessionMiddleware](middleware.md#sessionmiddleware)

## Change default backend

Pass `backend` property to `SessionMiddleware` arguments:

```python
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.sessions import CookieBackend

backend = CookieBackend(secret_key='secret', max_age=3600)

app = Starlette()
app.add_middleware(SessionMiddleware, backend=backend)
```

The default session backend is `CookieBackend`.

## Backends

### InMemoryBackend

Simply stores data in memory. The data is not persisted across requests. 
Mostly for use with unit tests.

### CookieBackend

Stores session data in a signed cookie on the client.  
This is the default backend.


## Custom backend

Create a class which implements the `starlette.sessions.SessionBackend` interface:

```python
from starlette.sessions import SessionBackend
from typing import Dict

# instance of class which manages session persistence

class InMemoryBackend(SessionBackend):
    def __init__(self):
        self._storage = {}

    async def read(self, session_id: str) -> Dict:
        """ Read session data from a data source using session_id. """
        return self._storage.get(session_id, {})

    async def write(self, data: Dict, session_id: str=None) -> str:
        """ Write session data into data source and return session id. """
        session_id = session_id or await self.generate_id()
        self._storage[session_id] = data
        return session_id

    async def remove(self, session_id: str):
        """ Remove session data. """
        del self._storage[session_id]

    async def exists(self, session_id: str)-> bool:
        return session_id in self._storage
```

Note that `write` has to return the session id. 

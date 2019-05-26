Enable sessions by using [SessionMiddleware](middleware.md#sessionmiddleware)

## Change default backend

Pass `backend` property to `SessionMiddleware` arguments:

```python
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.sessions import CookieBackend

backend = CookieBackend()

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

### RedisBackend

Uses Redis as session backend. This backend depends on an instance of 
redis connection or pool. 

`aioredis` library has to be installed.

```python
from starlette.sessions import RedisBackend
import aioredis

redis = await aioredis.create_redis('redis://localhost/0')
backend = RedisBackend(redis)
```

### MemcachedBackend

Uses Memcached as session backend. This backend depends on an instance of 
memcached connection. 

`aiomcache` library has to be installed.

```python
from starlette.sessions import MemcachedBackend
import aiomcache

client = aiomcache.Client('localhost')
backend = MemcachedBackend(client)
```

### DatabaseBackend

Uses SQL database as session backend. This backend requires an instance of 
`databases.Database` class. 

`databases` library has to be installed.

```python
from starlette.sessions import DatabaseBackend
import databases

client = databases.Database('sqlite://:memory')
await client.connect()

backend = DatabaseBackend(client)
```

Optionally, you can change the used table and column names:
```python
DatabaseBackend(client, table='sessions', id_column='id', data_column='data')
```

Note that the backend does not manage the database, you have to create 
needed tables before activating this backend.
 

## Custom backend

Create a class which implements the `starlette.sessions.SessionBackend` interface:

```python
from starlette.sessions import SessionBackend
from typing import Optional

# instance of class which manages session persistence
somedatasource = MyDataSource()

class MyCustomBackend(SessionBackend):
    async def read(self, session_id: str) -> Optional[str]:
        """ Read session data from a data source using session_id. """
        return somedatasource.find_by_id(session_id)

    async def write(self, session_id: str, data: str) -> str:
        """ Write session data into data source and return session id. """
        session_id = somedatasource.store(session_id, data)
        return session_id

    async def remove(self, session_id: str):
        """ Remove session data. """
        somedatasource.delete(session_id)
```

Note that `write` has to return the session id. 

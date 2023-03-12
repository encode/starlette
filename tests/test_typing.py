from contextlib import asynccontextmanager
from typing import AsyncIterator

from starlette.applications import Starlette


def test_lifespan_typing():
    class App(Starlette):
        pass

    @asynccontextmanager
    async def lifespan(app: App) -> AsyncIterator[None]:  # pragma: no cover
        yield

    App(lifespan=lifespan)

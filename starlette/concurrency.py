import asyncio
import functools
import typing
from typing import Any, AsyncGenerator, Iterator

try:
    import contextvars  # Python 3.7+ only.
except ImportError:  # pragma: no cover
    contextvars = None  # type: ignore


async def run_in_threadpool(
    func: typing.Callable, *args: typing.Any, **kwargs: typing.Any
) -> typing.Any:
    loop = asyncio.get_event_loop()
    if contextvars is not None:  # pragma: no cover
        # Ensure we run in the same context
        child = functools.partial(func, *args, **kwargs)
        context = contextvars.copy_context()
        func = context.run
        args = (child,)
    elif kwargs:  # pragma: no cover
        # loop.run_in_executor doesn't accept 'kwargs', so bind them in here
        func = functools.partial(func, **kwargs)
    return await loop.run_in_executor(None, func, *args)


class _StopSyncIteration(Exception):
    pass


def _interceptable_next(iterator: Iterator) -> Any:
    try:
        result = next(iterator)
        return result
    except StopIteration:
        raise _StopSyncIteration


async def iterator_to_async(iterator: Iterator) -> AsyncGenerator:
    while True:
        try:
            result = await run_in_threadpool(_interceptable_next, iterator)
            yield result
        except _StopSyncIteration:
            break

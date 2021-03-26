import functools
import sys
import typing
from typing import Any, AsyncGenerator, Iterator

import anyio

try:
    import contextvars  # Python 3.7+ only or via contextvars backport.
except ImportError:  # pragma: no cover
    contextvars = None  # type: ignore


T = typing.TypeVar("T")


async def run_until_first_complete(*args: typing.Tuple[typing.Callable, dict]) -> None:
    result: Any = None
    async with anyio.create_task_group() as task_group:

        async def task(_handler, _kwargs) -> Any:
            nonlocal result
            result = await _handler(**_kwargs)
            await task_group.cancel_scope.cancel()

        for handler, kwargs in args:
            await task_group.spawn(task, handler, kwargs)

    return result

async def run_in_threadpool(
    func: typing.Callable[..., T], *args: typing.Any, **kwargs: typing.Any
) -> T:
    if contextvars is not None:  # pragma: no cover
        # Ensure we run in the same context
        child = functools.partial(func, *args, **kwargs)
        context = contextvars.copy_context()
        func = context.run
        args = (child,)
    elif kwargs:  # pragma: no cover
        # run_sync doesn't accept 'kwargs', so bind them in here
        func = functools.partial(func, **kwargs)
    return await anyio.run_sync_in_worker_thread(func, *args)


class _StopIteration(Exception):
    pass


def _next(iterator: Iterator) -> Any:
    # We can't raise `StopIteration` from within the threadpool iterator
    # and catch it outside that context, so we coerce them into a different
    # exception type.
    try:
        return next(iterator)
    except StopIteration:
        raise _StopIteration


async def iterate_in_threadpool(iterator: Iterator) -> AsyncGenerator:
    while True:
        try:
            yield await anyio.run_sync_in_worker_thread(_next, iterator)
        except _StopIteration:
            break

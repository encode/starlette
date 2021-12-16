import functools
import typing
from typing import Any, AsyncGenerator, Awaitable, Iterator

import anyio

try:
    import contextvars  # Python 3.7+ only or via contextvars backport.
except ImportError:  # pragma: no cover
    contextvars = None  # type: ignore


T = typing.TypeVar("T")


async def run_until_first_complete(*args: typing.Tuple[typing.Callable, dict]) -> None:
    async with anyio.create_task_group() as task_group:

        async def run(func: typing.Callable[[], typing.Coroutine]) -> None:
            await func()
            task_group.cancel_scope.cancel()

        for func, kwargs in args:
            task_group.start_soon(run, functools.partial(func, **kwargs))


def bind_to_threadpool(
    func: typing.Callable[..., T]
) -> typing.Callable[..., Awaitable[T]]:
    def inner(*args: typing.Any, **kwargs: typing.Any) -> T:
        if contextvars is not None:  # pragma: no cover
            # Ensure we run in the same context
            child = functools.partial(func, *args, **kwargs)
            context = contextvars.copy_context()
            call = context.run
            args = (child,)
        elif kwargs:  # pragma: no cover
            # run_sync doesn't accept 'kwargs', so bind them in here
            call = functools.partial(func, **kwargs)
        return anyio.to_thread.run_sync(call, *args)

    return inner


async def run_in_threadpool(
    func: typing.Callable[..., T], *args: typing.Any, **kwargs: typing.Any
) -> T:
    return await bind_to_threadpool(func)(*args, **kwargs)


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
            yield await anyio.to_thread.run_sync(_next, iterator)
        except _StopIteration:
            break

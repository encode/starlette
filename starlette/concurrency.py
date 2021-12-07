import functools
import typing
from typing import Any, AsyncGenerator, Iterator

import anyio

try:
    import contextvars  # Python 3.7+ only or via contextvars backport.
    from contextvars import Context
except ImportError:  # pragma: no cover
    contextvars = None  # type: ignore
    Context = ContextVar = None  # type: ignore


T = typing.TypeVar("T")


def _restore_context(context: Context) -> None:
    """Copy the state of `context` to the current context."""
    for cvar in context:
        newval = context.get(cvar)
        try:
            if cvar.get() != newval:
                cvar.set(newval)
        except LookupError:
            # the context variable was first set inside of `context`
            cvar.set(newval)


async def run_until_first_complete(*args: typing.Tuple[typing.Callable, dict]) -> None:
    async with anyio.create_task_group() as task_group:

        async def run(func: typing.Callable[[], typing.Coroutine]) -> None:
            await func()
            task_group.cancel_scope.cancel()

        for func, kwargs in args:
            task_group.start_soon(run, functools.partial(func, **kwargs))


def _no_restore() -> None:
    ...  # pragma: no cover


async def run_in_threadpool(
    func: typing.Callable[..., T], *args: typing.Any, **kwargs: typing.Any
) -> T:
    if contextvars is not None:  # pragma: no cover
        # Ensure we run in the same context
        child = functools.partial(func, *args, **kwargs)
        context = contextvars.copy_context()
        restore = functools.partial(_restore_context, context)
        func = context.run
        args = (child,)
    elif kwargs:  # pragma: no cover
        # run_sync doesn't accept 'kwargs', so bind them in here
        restore = _no_restore
        func = functools.partial(func, **kwargs)
    res = await anyio.to_thread.run_sync(func, *args)
    restore()
    return res  # type: ignore


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

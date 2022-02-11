import functools
import sys
import typing

import anyio

if sys.version_info >= (3, 10):  # pragma: no cover
    from typing import ParamSpec
else:  # pragma: no cover
    from typing_extensions import ParamSpec
try:
    import contextvars  # Python 3.7+ only or via contextvars backport.
    from contextvars import Context
except ImportError:  # pragma: no cover
    contextvars = None  # type: ignore
    Context = None  # type: ignore


T = typing.TypeVar("T")
P = ParamSpec("P")


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


async def run_in_threadpool(
    func: typing.Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    if kwargs:  # pragma: no cover
        # run_sync doesn't accept 'kwargs', so bind them in here
        func = functools.partial(func, **kwargs)
    if contextvars is not None:
        context = contextvars.copy_context()
        func = functools.partial(context.run, func)  # type: ignore[assignment]
    else:  # pragma: no cover
        context = None
    res = await anyio.to_thread.run_sync(func, *args)
    if context is not None:
        _restore_context(context)
    return res


class _StopIteration(Exception):
    pass


def _next(iterator: typing.Iterator[T]) -> T:
    # We can't raise `StopIteration` from within the threadpool iterator
    # and catch it outside that context, so we coerce them into a different
    # exception type.
    try:
        return next(iterator)
    except StopIteration:
        raise _StopIteration


async def iterate_in_threadpool(
    iterator: typing.Iterator[T],
) -> typing.AsyncIterator[T]:
    while True:
        try:
            yield await anyio.to_thread.run_sync(_next, iterator)
        except _StopIteration:
            break

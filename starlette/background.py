import inspect
import typing

from starlette.concurrency import run_in_threadpool


def iscoroutinefunction(obj: object) -> bool:
    if inspect.iscoroutinefunction(obj):
        return True
    return callable(obj) and inspect.iscoroutinefunction(obj.__call__)


class BackgroundTask:
    def __init__(
        self, func: typing.Callable, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.is_async = iscoroutinefunction(func)

    async def __call__(self) -> None:
        if self.is_async:
            await self.func(*self.args, **self.kwargs)
        else:
            await run_in_threadpool(self.func, *self.args, **self.kwargs)


class BackgroundTasks(BackgroundTask):
    def __init__(self, tasks: typing.Sequence[BackgroundTask] = None):
        self.tasks = list(tasks) if tasks else []

    def add_task(
        self, func: typing.Callable, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        task = BackgroundTask(func, *args, **kwargs)
        self.tasks.append(task)

    async def __call__(self) -> None:
        for task in self.tasks:
            await task()

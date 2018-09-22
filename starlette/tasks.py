import uuid
import asyncio
import functools

class BackgroundTask:
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    async def __call__(self):
        if asyncio.iscoroutinefunction(self.func):
            self._result = await asyncio.ensure_future(
                self.func(*self.args, **self.kwargs)
            )
        else:
            fn = functools.partial(self.func, *self.args, **self.kwargs)
            loop = asyncio.get_event_loop()
            self._result = await loop.run_in_executor(None, fn)

    @property
    def id(self):
        if not hasattr(self, "_id"):
            self._id = str(uuid.uuid4())
        return self._id

    @property
    def result(self):
        return getattr(self, '_result', None)

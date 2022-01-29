import functools

from starlette._utils import iscoroutinefunction


def test_async_func():
    async def async_func():
        ...

    def func():
        ...

    assert iscoroutinefunction(async_func)
    assert not iscoroutinefunction(func)


def test_async_partial():
    async def async_func(a, b):
        ...

    def func(a, b):
        ...

    partial = functools.partial(async_func, 1)
    assert iscoroutinefunction(partial)

    partial = functools.partial(func, 1)
    assert not iscoroutinefunction(partial)


def test_async_method():
    class Async:
        async def method(self):
            ...

    class Sync:
        def method(self):
            ...

    assert iscoroutinefunction(Async().method)
    assert not iscoroutinefunction(Sync().method)


def test_async_object_call():
    class Async:
        async def __call__(self):
            ...

    class Sync:
        def __call__(self):
            ...

    assert iscoroutinefunction(Async())
    assert not iscoroutinefunction(Sync())


def test_async_partial_object_call():
    class Async:
        async def __call__(self, a, b):
            ...

    class Sync:
        def __call__(self, a, b):
            ...

    partial = functools.partial(Async(), 1)
    assert iscoroutinefunction(partial)

    partial = functools.partial(Sync(), 1)
    assert not iscoroutinefunction(partial)

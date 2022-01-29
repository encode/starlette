import functools

from starlette._utils import iscoroutinefunction


def test_async_func():
    async def async_func():
        ...  # pragma: no cover

    def func():
        ...  # pragma: no cover

    assert iscoroutinefunction(async_func)
    assert not iscoroutinefunction(func)


def test_async_partial():
    async def async_func(a, b):
        ...  # pragma: no cover

    def func(a, b):
        ...  # pragma: no cover

    partial = functools.partial(async_func, 1)
    assert iscoroutinefunction(partial)

    partial = functools.partial(func, 1)
    assert not iscoroutinefunction(partial)


def test_async_method():
    class Async:
        async def method(self):
            ...  # pragma: no cover

    class Sync:
        def method(self):
            ...  # pragma: no cover

    assert iscoroutinefunction(Async().method)
    assert not iscoroutinefunction(Sync().method)


def test_async_object_call():
    class Async:
        async def __call__(self):
            ...  # pragma: no cover

    class Sync:
        def __call__(self):
            ...  # pragma: no cover

    assert iscoroutinefunction(Async())
    assert not iscoroutinefunction(Sync())


def test_async_partial_object_call():
    class Async:
        async def __call__(self, a, b):
            ...  # pragma: no cover

    class Sync:
        def __call__(self, a, b):
            ...  # pragma: no cover

    partial = functools.partial(Async(), 1)
    assert iscoroutinefunction(partial)

    partial = functools.partial(Sync(), 1)
    assert not iscoroutinefunction(partial)

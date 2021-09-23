from starlette.utils import iscoroutinefunction


def test_is_coroutine_function():
    async def func():
        pass  # pragma: no cover

    assert iscoroutinefunction(func)


def test_is_not_coroutine_function():
    def func():
        pass  # pragma: no cover

    assert not iscoroutinefunction(func)


def test_is_async_callable():
    class async_callable_obj:
        async def __call__(self):
            pass  # pragma: no cover

    assert iscoroutinefunction(async_callable_obj())


def test_is_not_asnyc_callable():
    class callable_obj:
        def __call__(self):
            pass  # pragma: no cover

    assert not iscoroutinefunction(callable_obj())

import inspect


def iscoroutinefunction(obj: object) -> bool:
    if inspect.iscoroutinefunction(obj):
        return True
    return callable(obj) and inspect.iscoroutinefunction(obj.__call__)

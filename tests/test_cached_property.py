from pytest import raises

from starlette.cached_property import cached_property


def test_cached_property_cache_attributes():
    class _Class:
        @cached_property
        def prop(self):
            return []

    obj = _Class()
    assert obj.prop is obj.prop

    other = _Class()
    # different instances of same class must has different cached properties
    assert obj.prop is not other.prop


def test_get_cached_property_on_class():
    @cached_property
    def prop(instance):  # pragma: no cover
        pass

    class _Class:
        foo = prop

    assert _Class.foo is prop


def test_cached_property_set_name_twice():
    with raises(RuntimeError):

        class _Class:
            @cached_property
            def prop(self):  # pragma: no cover
                pass

            another_prop = prop


def test_get_cached_property_without_attrname():
    class _Class:
        pass

    @cached_property
    def prop(instance):  # pragma: no coverage
        pass

    _Class.prop = prop

    obj = _Class()

    with raises(
        TypeError,
        match="Cannot use cached_property instance without calling __set_name__ on it.",
    ):
        obj.prop


def test_get_cached_property_on_class_without_dict():
    class _Class:
        __slots__ = ()

        @cached_property
        def prop(self):  # pragma: no coverage
            pass

    obj = _Class()

    with raises(TypeError, match=f"No '__dict__' attribute on.*"):
        obj.prop

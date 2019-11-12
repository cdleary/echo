new_count = 0
meta_new_args = None

class MyMeta(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        # Capture the passed args for later comparison.
        global meta_new_args
        assert meta_new_args is None
        meta_new_args = (mcls, name, bases, namespace, kwargs)

        s = super(MyMeta, mcls)
        super_new = s.__new__
        assert super_new is type.__new__
        cls = super_new(mcls, name, bases, namespace)
        return cls


class Foo(metaclass=MyMeta):
    pass


assert meta_new_args == (
    MyMeta, 'Foo', (),
    {'__module__': '__main__', '__qualname__': 'Foo'},
    {}), meta_new_args

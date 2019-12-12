meta_new_args = None
CALL_METHOD = False

class MyMeta(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        # Capture the passed args for later comparison.
        global meta_new_args
        assert meta_new_args is None
        meta_new_args = (mcls, name, bases, namespace, kwargs)

        if CALL_METHOD:
            cls = super(MyMeta, mcls).__new__(mcls, name, bases, namespace)
        else:
            s = super(MyMeta, mcls)
            super_new = s.__new__
            assert super_new is type.__new__
            cls = super_new(mcls, name, bases, namespace)
        return cls


# One class where we don't do a method-style call to super.
class Foo(metaclass=MyMeta):
    pass


assert meta_new_args == (
    MyMeta, 'Foo', (),
    {'__module__': '__main__', '__qualname__': 'Foo'},
    {}), meta_new_args
meta_new_args = None


CALL_METHOD = True


# One class where do a method-style call to super.
class Bar(metaclass=MyMeta):
    pass


assert meta_new_args == (
    MyMeta, 'Bar', (),
    {'__module__': '__main__', '__qualname__': 'Bar'},
    {}), meta_new_args

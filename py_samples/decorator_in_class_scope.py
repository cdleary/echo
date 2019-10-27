def decorator(f):
    return f


def wrapper(f):
    def wraps_f(*args, **kwargs):
        return f(*args, **kwargs)
    return wraps_f


class Foo:

    @decorator
    def my_method(self):
        return 42

    @wrapper
    def wrapped_method(self):
        return 77


foo = Foo()
assert foo.my_method() == 42
assert foo.wrapped_method() == 77

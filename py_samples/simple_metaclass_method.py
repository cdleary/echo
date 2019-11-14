class MyMeta(type):
    def f(cls, value):
        first = cls.g()
        return (first, value)
    def g(cls):
        return cls


class Foo(metaclass=MyMeta):
    pass


assert Foo.f(42) == (Foo, 42)

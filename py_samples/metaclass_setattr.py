seen = []


class MyMeta(type):
    def __setattr__(cls, name, value):
        seen.append((cls, name, value))


class MyClass(metaclass=MyMeta):
    pass


MyClass.foo = 42
assert not hasattr(MyClass, 'foo')
MyClass.bar = 64
assert not hasattr(MyClass, 'bar')
assert seen == [(MyClass, 'foo', 42), (MyClass, 'bar', 64)], seen

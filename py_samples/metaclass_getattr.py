class MyMeta(type):
    def __getattr__(self, name):
        return 42


class MyClass(metaclass=MyMeta):
    pass


assert MyClass.foo == 42
assert MyClass.bar == 42

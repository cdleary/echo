class MyMeta(type):
    def __getitem__(cls, name):
        assert isinstance(cls, MyMeta), cls
        return 42


class MyClass(metaclass=MyMeta):
    pass


class Derived(MyClass):
    pass


assert MyClass['foo'] == 42
assert Derived['bar'] == 42

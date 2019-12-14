class MyMeta(type):
    @property
    def my_property(cls):
        return cls.value


class Foo(metaclass=MyMeta):
    value = 42


assert Foo.my_property == 42

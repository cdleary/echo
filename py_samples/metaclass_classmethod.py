class MyMeta(type):
    x = 42
    @classmethod
    def f(cls):
        assert cls is MyMeta, cls
        return cls.x


class MyClass(metaclass=MyMeta): pass


assert MyClass.f() == 42

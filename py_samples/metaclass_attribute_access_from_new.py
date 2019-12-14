class MyMeta(type):
    value = 42

    def __new__(mcls, name, bases, namespace, **kwargs):
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        cls.v = MyMeta.value
        return cls


class Base(metaclass=MyMeta): pass


assert Base.v == 42

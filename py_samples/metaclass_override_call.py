class MyMeta(type):
    def __call__(cls):
        return 42


class MyClass(metaclass=MyMeta):
    pass


assert MyClass() == 42

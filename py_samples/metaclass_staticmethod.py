class MyMeta(type):
    @staticmethod
    def foo():
        return 42


class MyClass(metaclass=MyMeta):
    pass



assert MyClass.foo() == 42

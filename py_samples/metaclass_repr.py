class MyMeta(type):
    def __repr__(cls):
        return 'shoobadooba: ' + cls.__name__


class MyClass(metaclass=MyMeta):
    pass


assert repr(MyClass) == 'shoobadooba: MyClass', repr(MyClass)
assert repr(MyMeta).endswith("class '__main__.MyMeta'>"), repr(MyMeta)

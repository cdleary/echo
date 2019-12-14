class MyMeta(type):
    attr = 42


class Bar(metaclass=MyMeta):
    pass


assert Bar.attr == 42

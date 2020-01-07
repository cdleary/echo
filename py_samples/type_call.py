class Foo:
    def __init__(self, x):
        self.x = x


assert type(Foo) is type
o = type(Foo).__call__(Foo, 42)
assert isinstance(o, Foo), o
assert o.x == 42, o.x


class Bar:
    def __init__(self):
        self.x = 64


assert type(Bar) is type
o = type(Bar).__call__(Bar)
assert isinstance(o, Bar), o
assert o.x == 64

class OverridingDesc:
    def __get__(self, obj, objtype): return 42
    def __set__(self, obj, value): pass


class Foo:
    def __init__(self):
        self.__dict__['foo'] = 64

    foo = OverridingDesc()



f = Foo()
assert f.foo == 42, f.foo
f.foo = 128
assert f.foo == 42
assert f.__dict__['foo'] == 64, f.__dict__

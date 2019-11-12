class NonOverridingDesc:
    def __get__(self, obj, objtype): return 42


class Foo:
    def __init__(self):
        self.__dict__['foo'] = 64

    foo = NonOverridingDesc()



f = Foo()
assert f.foo == 64

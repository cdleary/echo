class NonOverridingDesc:
    def __get__(self, obj, objtype): raise NotImplementedError


class Foo:
    def __init__(self):
        self.__dict__['foo'] = 64

    foo = NonOverridingDesc()



f = Foo()
assert f.foo == 64

class OverridingDesc:
    def __get__(self, obj, objtype): return 42
    def __set__(self, obj, value): pass


class Foo:
    def __init__(self):
        self.__dict__['foo'] = 64

    foo = OverridingDesc()



o = Foo()
assert hasattr(Foo.__dict__['foo'], '__get__')
assert hasattr(Foo.__dict__['foo'], '__set__')
assert o.foo == 42, o.foo
o.foo = 128
assert o.foo == 42
assert o.__dict__['foo'] == 64, o.__dict__

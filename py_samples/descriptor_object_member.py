class MyDescriptor:
    def __get__(self, obj, objtype):
        return 42



class Dummy: pass


o = Dummy()
d = MyDescriptor()
o.foo = d
assert o.foo is d


Dummy.bar = d
assert Dummy.bar == 42

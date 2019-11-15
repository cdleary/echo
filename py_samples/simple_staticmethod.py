def f(): return 42


class Foo:
    f = staticmethod(f)


o = Foo()
d = Foo.__dict__['f']
assert type(d) is staticmethod
assert d.__func__ is f
assert d.__get__(d) is f
assert o.f is f
assert o.f() == 42

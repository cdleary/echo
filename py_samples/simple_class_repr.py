class Foo: pass


assert type(Foo).__repr__ is type.__repr__
r = repr(Foo)
assert "class '__main__.Foo'>" in r, r

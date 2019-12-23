class Foo: pass


assert Foo.__mro__ == (Foo, object)
assert type(Foo).__repr__ is type.__repr__
r = repr(Foo)
assert "class '__main__.Foo'>" in r, r

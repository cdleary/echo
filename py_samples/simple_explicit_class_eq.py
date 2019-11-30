class Foo: pass


f = Foo()
g = Foo()

r = f.__eq__(g)
assert r is NotImplemented, r
r = f.__ne__(g)
assert r is NotImplemented, r

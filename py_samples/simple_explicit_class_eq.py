class Foo: pass


f = Foo()
g = Foo()

assert not f.__eq__(g)

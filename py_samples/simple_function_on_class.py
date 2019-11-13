def f(x): return x

class Foo:
    foo_f = f


assert Foo.foo_f is f, Foo.foo_f
assert Foo.foo_f(42) == 42

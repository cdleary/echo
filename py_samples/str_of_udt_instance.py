class Foo:
    def __str__(self): return 'foo'


f = Foo()
assert str(f) == 'foo'

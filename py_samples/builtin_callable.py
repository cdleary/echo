assert callable(callable)

f = lambda: None
assert callable(f)


class Foo: pass
assert callable(Foo), 'Class should be callable'
assert hasattr(Foo, '__call__')


class MyClass:
    def __call__(self): pass


o = MyClass()
assert callable(o)

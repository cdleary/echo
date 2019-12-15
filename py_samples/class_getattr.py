class MyClass:
    def __getattr__(self, name):
        return 42


o = MyClass()
assert hasattr(o, 'foo')
assert o.foo == 42
assert hasattr(o, 'bar')
assert o.bar == 42

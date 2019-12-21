class MyClass:
    def __call__(self, x): return x

o = MyClass()
assert o(42) == 42
assert o('foo') == 'foo'

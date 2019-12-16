class MyClass:
    pass


o = MyClass()
sa = o.__setattr__
sa('foo', 42)
assert o.foo == 42

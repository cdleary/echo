class MyClass:
    def __init__(self, x):
        self.x = x


o = MyClass(42)
assert isinstance(o, MyClass), o
assert isinstance(o, object), o
assert o.x == 42

class MyClass: pass


o = MyClass()
assert isinstance(o, MyClass), o
assert isinstance(o, object), o

class MyClass: pass


assert MyClass.__bases__ == (object,), MyClass.__bases__
assert MyClass.__mro__ == (MyClass, object), MyClass.__mro__

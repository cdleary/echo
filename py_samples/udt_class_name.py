class MyClass: pass


o = MyClass()
assert o.__class__ is MyClass
assert o.__class__.__name__ == 'MyClass'

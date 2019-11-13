class MyClass:
    x = 42


def my_function(c):
    assert c is MyClass, c
    return c.x


cm = classmethod(my_function)
print('cm:                         ', cm)
print('cm.__func__:                ', cm.__func__)
print('cm.__get__(None, MyClass):  ', cm.__get__(None, MyClass))
print('cm.__get__(None, MyClass)():', cm.__get__(None, MyClass)())

assert cm.__func__ is my_function
assert cm.__get__(None, MyClass).__self__ is MyClass

f = cm.__get__(None, MyClass)
assert not isinstance(f, int), f
assert f() == 42

def f(cls):
    assert cls is MyClass, cls
    return cls.value


class MyClass:
    value = 42

    f = classmethod(f)


assert type(MyClass.__dict__['f']) is classmethod, type(MyClass.__dict__['f']) 

assert MyClass.f != 42, MyClass.__dict__

# Retrieve the bound classmethod.
assert hasattr(MyClass.f, '__func__'), MyClass.f
assert hasattr(MyClass.f, '__self__'), MyClass.f

assert MyClass.f.__self__ is MyClass, MyClass.f.__self__
assert MyClass.f.__func__ is f, MyClass.f.__func__

assert type(MyClass.f) is not type(MyClass.__dict__['f'])
assert MyClass.f() == 42

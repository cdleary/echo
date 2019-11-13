def f(x): return x
class Foo: pass


FunctionType = type(f)
assert f.__class__ is FunctionType
assert hasattr(FunctionType, '__get__')
assert FunctionType.__get__(f, None, Foo) is f
assert f.__get__(None, Foo) is f, f.__get__(None, Foo)

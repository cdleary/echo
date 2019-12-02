def f(x): return x
class Foo: pass


FunctionType = type(f)
print('FunctionType is %s' % FunctionType)
print(type(FunctionType))
assert type(FunctionType) is type, type(FunctionType)
assert f.__class__ is FunctionType
assert hasattr(FunctionType, '__get__')

ftg = FunctionType.__get__
assert ftg(f, None, Foo) is f

fg = f.__get__
assert fg(None, Foo) is f, fg(None, Foo)

r = f.__get__(None, Foo)
assert r is fg(None, Foo)

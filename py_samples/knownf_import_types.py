import types


def foo():
    yield 1


gen = foo()
print(type(gen))
assert isinstance(gen, types.GeneratorType), type(gen)

def g():
    i = 42
    yield i
    i += 22
    yield i


i = g()
assert next(i) == 42
assert next(i) == 64

try:
    next(i)
except StopIteration:
    assert True
else:
    assert False

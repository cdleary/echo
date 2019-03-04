def g():
    yield


i = g()
assert next(i) is None

try:
    next(i)
except StopIteration:
    assert True
else:
    assert False

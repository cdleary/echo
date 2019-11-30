def f(*items, last):
    return (items, last)

try:
    t = f('a', 'b', 'c', 'd')
except TypeError as e:
    assert "required keyword-only argument: 'last'" in str(e)
else:
    assert False

try:
    t = f('a')
except TypeError as e:
    assert "required keyword-only argument: 'last'" in str(e)
else:
    assert False

t = f('a', 'b', 'c', last='d')
assert t == (('a', 'b', 'c'), 'd'), t
t = f(last='a')
assert t == ((), 'a')
t = f('a', last='b')
assert t == (('a',), 'b')

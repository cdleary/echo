def g(first, *items, last):
    return (first, items, last)


try:
    t = g(1, 2, 3, 4)
except TypeError as e:
    assert "missing 1 required keyword-only argument: 'last'" in str(e), e
else:
    assert False, 'Should have flagged missing kwonlyarg.'

t = g(1, 2, 3, last=4)
assert t == (1, (2, 3), 4), t
t = g(1, 2, last=3)
assert t == (1, (2,), 3), t
t = g(1, last=2)
assert t == (1, (), 2), t

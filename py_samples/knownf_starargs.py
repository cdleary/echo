def f(*items, last):
    return (items, last)


assert f(1, 2, 3, 4) == ((1, 2, 3), 4)
assert f(1) == ((), 1)
assert f(1, 2) == ((1,), 2)

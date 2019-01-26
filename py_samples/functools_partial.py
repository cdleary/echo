import functools


def add(x, y):
    return x + y


add1 = functools.partial(add, 1)
assert add1(2) == 3
assert add1(-1) == 0

four = functools.partial(add, 1, 3)
assert four() == 4

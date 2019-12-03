def my_generator():
    yield 1
    yield 2
    yield 3


r = list(my_generator())
assert r == [1, 2, 3], r

def my_generator():
    yield 'a', 1
    yield 'b', 2
    yield 'c', 3


d = dict(my_generator())
assert d == dict(a=1, b=2, c=3), d

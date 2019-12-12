def my_generator():
    yield 1
    yield 2
    yield 3


assert tuple(my_generator()) == (1, 2, 3)

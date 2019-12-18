def my_generator():
    yield 1
    yield 2
    yield 3


g = my_generator()
for i, item in enumerate(g, start=1):
    assert i == item, (i, item)


assert i == 3

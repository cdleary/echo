def decorate(f): return f


@decorate
def tuplify(x, y):
    return (x, y)


assert tuplify(1, 2) == (1, 2)

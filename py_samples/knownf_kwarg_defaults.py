def tup3(x, y, z):
    return (x, y, z)


assert tup3(z=1, y=3, x=4) == (4, 3, 1)


def foo(x, *, y=2, z=3):
    return x+y+z


assert foo(1) == 6

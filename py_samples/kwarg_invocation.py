# Uses keyword arguments on the invocation side (for positional parameters).


def tup3(x, y, z):
    return (x, y, z)


t = tup3(z=1, y=3, x=4)
assert t == (4, 3, 1), t

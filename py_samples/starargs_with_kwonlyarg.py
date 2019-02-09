def g(first, *items, last):
    return (first, items, last)


t = g(1, 2, 3, 4)
assert t == (1, (2, 3), 4), t
t = g(1, 2, 3)
assert t == (1, (2,), 3), t
t = g(1, 2)
assert t == (1, (), 2), t

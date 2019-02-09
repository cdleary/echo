def f(*items, last):
    return (items, last)


t = f('a', 'b', 'c', 'd')
assert t == (('a', 'b', 'c'), 'd'), t
t = f('a')
assert t == ((), 'a')
t = f('a', 'b')
assert t == (('a',), 'b')

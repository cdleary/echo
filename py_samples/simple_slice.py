t = (0, 1, 2, 3, 4)
assert t[:1] == t[0:1] == (0,)
assert t[::-1] == tuple(reversed(t)) == (4, 3, 2, 1, 0)
assert t[1:3] == (1, 2)

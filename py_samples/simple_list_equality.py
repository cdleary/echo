xs = [1, 2, 3]
ys = (1, 2, 3)  # tuple!
zs = [1] + [2] + [3]

assert (xs == xs) is True
assert (xs == zs) is True
assert (zs == zs) is True
assert (xs == ys) is False
assert (ys == zs) is False

assert ([] == []) is True
assert ([1] == []) is False
assert ([1] == [2]) is False

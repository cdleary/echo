t = (1, 2, 3, 4, 5, 6)
a, b, c, *rest = t
assert a == 1, a
assert b == 2, b
assert c == 3, c
assert rest == [4, 5, 6], rest

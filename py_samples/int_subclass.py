class MyInt(int): pass


i = int.__new__(MyInt, 42)
assert type(i) is MyInt
assert type(i+1) is int, type(i+1)
assert int(i) == 42, int(i)
assert i == 42
assert i & 7 == 2
assert 7 & i == 2
assert i * 2 == 84, (i*2)
assert 2 * i == 84
assert bool(i) is True, bool(i)

assert i < 43

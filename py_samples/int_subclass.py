class MyInt(int): pass


i = int.__new__(MyInt, 42)
assert type(i) is MyInt
assert type(i+1) is int, type(i+1)

assert i < 43

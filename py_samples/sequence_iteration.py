class MyClass:
    def __getitem__(self, i):
        if i == 0: return 8
        elif i == 1: return 9
        elif i == 2: return 10
        else: raise IndexError


it = iter(MyClass())
assert next(it) == 8
assert next(it) == 9
assert next(it) == 10
try:
    next(it)
except StopIteration:
    pass
else:
    assert False

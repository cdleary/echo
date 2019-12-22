class MyClass:
    def __init__(self, value):
        self.value = value
    def __len__(self):
        return self.value


o = MyClass(42)
assert len(o) == 42
assert bool(o) is True

p = MyClass(-1)
try:
    len(p)
except ValueError as e:
    assert '__len__() should return >= 0' == e.args[0]
else:
    assert False, 'Should have flagged ValueError for len'

try:
    assert bool(p) is True
except ValueError as e:
    assert '__len__() should return >= 0' == e.args[0]
else:
    assert False, 'Should have flagged ValueError for bool'

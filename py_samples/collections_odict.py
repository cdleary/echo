from collections import OrderedDict as odict


o = odict()
o['foo'] = 42
o['bar'] = 64

it = iter(o)
assert next(it) == 'foo'
assert next(it) == 'bar'

try:
    next(it)
except StopIteration:
    pass
else:
    raise AssertionError

import pprint

s = pprint.pformat(list(dict(foo=[1, 2, 3], bar=('a', 'b', 'c')).items()))
assert s == "[('foo', [1, 2, 3]), ('bar', ('a', 'b', 'c'))]", repr(s)

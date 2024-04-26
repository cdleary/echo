class MyDict(dict): pass


assert MyDict.__mro__ == (MyDict, dict, object), MyDict.__mro__
d = MyDict()
assert isinstance(d, MyDict), type(d)
assert issubclass(MyDict, dict)
d.update(dict(k=42))
assert d == {'k': 42}
d.setdefault('k', 64)
assert d == {'k': 42}
d.setdefault('m', 64)
assert d == {'k': 42, 'm': 64}
assert d.pop('k') == 42
assert d == {'m': 64}

assert 'm' in d, d
assert 'n' not in d, d

assert dict(d) == {'m': 64}

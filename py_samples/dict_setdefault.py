d = {}
d.setdefault('k', 42)
assert d['k'] == 42
d.setdefault('k', 77)
assert d['k'] == 42

dict.setdefault(d, 'k2', 128)
assert d['k2'] == 128
assert 'k' in d
assert 'k2' in d

d = {}
d.update(x=4, y='str')
assert 'x' in d
assert 'y' in d
assert d['x'] == 4
assert d['y'] == 'str'
assert d == {'x': 4, 'y': 'str'}
assert sorted(list(d.items())) == [('x', 4), ('y', 'str')]

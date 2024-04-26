assert None == None  # nopep8: for testing purposes
assert None is None
assert () == ()
assert (None,) == (None,)
assert (0,) == (False,)
assert (1, 2, 3) == (1, 2, 3)
assert 'foo' in 'foobar'
assert dict(foo=2, bar=7) == {'foo': 2, 'bar': 7}

d = dict(x='foo', y='bar')
assert 'foo' in d.values()
assert 'bar' in d.values()
assert 'foobar' not in d.values()

lst = ['foo', 'bar']
assert 'foo' in lst
assert 'foobar' not in lst

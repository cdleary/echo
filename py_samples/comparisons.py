assert None == None  # nopep8: for testing purposes
assert None is None
assert () == ()
assert (None,) == (None,)
assert (0,) == (False,)
assert (1, 2, 3) == (1, 2, 3)
assert 'foo' in 'foobar'
assert dict(foo=2, bar=7) == {'foo': 2, 'bar': 7}

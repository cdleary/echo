try:
    {}['foo']
except KeyError as e:
    assert "KeyError('foo')" == repr(e), repr(e)
else:
    assert False

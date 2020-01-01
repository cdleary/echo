d = {}
try:
    del d['missing']
except KeyError as e:
    assert repr(e) == "KeyError('missing')", repr(e)
else:
    raise AssertionError

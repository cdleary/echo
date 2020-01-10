assert max([1, 2, 3, 4]) == 4

try:
    max([])
except ValueError as e:
    assert repr(e) == "ValueError('max() arg is an empty sequence')", repr(e)
else:
    assert False, 'Did not see ValueError'

try:
    max(range(0, 0))
except ValueError as e:
    assert repr(e) == "ValueError('max() arg is an empty sequence')", repr(e)
else:
    assert False, 'Did not see ValueError'

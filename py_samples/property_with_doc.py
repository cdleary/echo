p = property(lambda self: 42, doc='meaning of life')
assert p.__doc__ == 'meaning of life'
assert p.__get__(p, None) == 42

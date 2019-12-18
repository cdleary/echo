assert Exception.__new__(Exception).args == ()
assert Exception.__new__(Exception, 'oh hi').args == ('oh hi',)
assert Exception.__new__(Exception, 42, 64.0).args == (42, 64.0)

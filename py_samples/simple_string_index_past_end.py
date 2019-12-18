s = ''
try:
    s[0]
except IndexError as e:
    assert str(e) == 'string index out of range', str(e)
else:
    assert False

x = 42
try:
    x()
except TypeError as e:
    assert "'int' object" in str(e), e
    assert 'is not callable' in str(e), e
else:
    assert False

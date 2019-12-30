foo = 42
assert 'foo' in dir()
assert isinstance(dir(), list), dir()


def f():
    bar = 64
    d = dir()
    assert isinstance(d, list), d
    assert 'bar' in d, d
    assert 'foo' not in d, d


f()

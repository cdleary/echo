import sys

print('starting', file=sys.stderr)

foo = 42
assert 'foo' in dir()
print('global nullary dir ok', file=sys.stderr)
assert isinstance(dir(), list), dir()


def f():
    bar = 64
    d = dir()
    print('local nullary dir ok', file=sys.stderr)
    assert isinstance(d, list), d
    assert 'bar' in d, d
    assert 'foo' not in d, d


f()

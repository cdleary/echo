class MyClass:
    foo = 42
    bar = foo
    del foo


assert 'foo' not in MyClass.__dict__
assert 'bar' in MyClass.__dict__

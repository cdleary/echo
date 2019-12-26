class MyClass: pass


try:
    it = iter(MyClass())
except TypeError as e:
    assert str(e) == "'MyClass' object is not iterable"
else:
    assert False, 'MyClass instance should not be iterable'

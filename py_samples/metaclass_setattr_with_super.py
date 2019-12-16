reentered = False

class MyMeta(type):
    def __setattr__(self, name, value):
        global reentered
        assert not reentered
        reentered = True
        if name == 'foo':
            raise ValueError
        super().__setattr__(name, value)


class MyClass(metaclass=MyMeta):
    pass


MyClass.bar = 42
assert 'bar' in MyClass.__dict__, MyClass.__dict__
assert MyClass.bar == 42

reentered = False

try:
    MyClass.foo = 42
except ValueError:
    pass
else:
    assert False

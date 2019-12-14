class MyProperty:
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, obj, objtype):
        assert type(self) is MyProperty, (self, type(self))
        f = self.fget
        assert f(obj) == self.fget(obj)
        return self.fget(obj)


class ClassWithProperty:
    @MyProperty
    def stuff(self):
        return 42


descr = ClassWithProperty.__dict__['stuff']
#assert isinstance(descr, MyProperty), descr
assert hasattr(descr, 'fget'), descr
#cwp = ClassWithProperty()
#assert cwp.stuff == 42

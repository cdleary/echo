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


cwp = ClassWithProperty()
assert cwp.stuff == 42

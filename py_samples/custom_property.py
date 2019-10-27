class MyProperty:
    def __init__(self, fget):
        print('fget:', fget)
        self.fget = fget

    def __get__(self, obj, objtype=None):
        f = self.fget
        print('f:', f)
        assert f(obj) == self.fget(obj)
        return self.fget(obj)


class ClassWithProperty:
    @MyProperty
    def stuff(self):
        print('stuff self:', self)
        return 42

    print('ClassWithProperty.stuff:', stuff)


cwp = ClassWithProperty()
assert cwp.stuff == 42

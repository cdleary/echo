class MyDict:
    def __init__(self): self._wrapped = {}
    def __getitem__(self, k): self._wrapped[k]
    def __setitem__(self, k, v): self._wrapped[k] = v


checked = False


class MyMeta(type):
    @classmethod
    def __prepare__(mcls, name, bases, **kwargs):
        print(mcls, name, bases, kwargs)
        return MyDict()

    def __new__(cls, name, bases, classdict):
        global checked
        checked = True
        assert isinstance(classdict, MyDict), classdict


assert not checked


class MyClass(metaclass=MyMeta):
    pass


assert checked

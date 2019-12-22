class MyDict:
    def __init__(self): self._wrapped = {}
    def __repr__(self): return 'MyDict({!r})'.format(self._wrapped)
    def __getitem__(self, k): self._wrapped[k]
    def __setitem__(self, k, v): self._wrapped[k] = v


checked = None


class MyMeta(type):
    @classmethod
    def __prepare__(mcls, name, bases, **kwargs):
        print('MyMeta.__prepare__:', mcls, name, bases, kwargs)
        return MyDict()

    def __new__(cls, name, bases, classdict):
        global checked
        checked = 'MyMeta'
        print('classidct:', classdict)
        assert isinstance(classdict, MyDict), classdict


assert not checked


class MyClass(metaclass=MyMeta):
    def __new__(cls, name, bases, classdict):
        global checked
        checked = 'MyClass'
        assert isinstance(classdict, MyDict), classdict


assert checked == 'MyMeta'

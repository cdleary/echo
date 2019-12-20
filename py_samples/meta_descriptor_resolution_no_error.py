class MyMeta(type):
    def __getattr__(self, name):
        raise NotImplementedError(name)


class MyBase(metaclass=MyMeta):
    pass


class MyDerived(MyBase):
    def __init__(self):
        self.__dict__['foo'] = 42


o = MyDerived()
assert o.foo == 42
try:
    MyBase.foo
except NotImplementedError as e:
    assert 'foo' in str(e)
else:
    assert False, 'Did not see error from metaclass.'

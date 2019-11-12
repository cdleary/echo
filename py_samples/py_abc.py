from _py_abc import ABCMeta


assert ABCMeta.__bases__ == (type,)
assert hasattr(ABCMeta, '__subclasshook__')


class MyABC(metaclass=ABCMeta): pass
class Foo(MyABC): pass


assert MyABC in Foo.__mro__
assert Foo.__mro__ == getattr(Foo, '__mro__', ())


assert Foo.__bases__ == (MyABC,)
assert MyABC.__subclasses__() == [Foo]
assert issubclass(Foo, MyABC)

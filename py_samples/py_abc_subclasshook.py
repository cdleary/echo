from _py_abc import ABCMeta


invocation = None


class MyABC(metaclass=ABCMeta):
    @classmethod
    def __subclasshook__(cls, C):
        global invocation
        invocation = (cls, C)
        return False



class Derived(MyABC): pass


assert not issubclass(Derived, MyABC)
assert invocation == (MyABC, Derived), invocation

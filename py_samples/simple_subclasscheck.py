saw = None

class Hooked(type):
    def __subclasscheck__(cls, subclass):
        global saw
        print('__subclasscheck__: {} {}'.format(cls, subclass))
        saw = (cls, subclass)
        return False

class HookedBase(metaclass=Hooked):
    pass


class Derived(HookedBase):
    pass


assert not issubclass(Derived, HookedBase)
assert issubclass(Derived, object)
assert saw == (HookedBase, Derived), saw

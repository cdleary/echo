class Hooked(type):
    def __subclasscheck__(cls, subclass):
        assert cls is HookedBase, cls
        assert subclass is Derived, subclass
        return False


class HookedBase(metaclass=Hooked):
    pass


class Derived(HookedBase):
    pass


assert not issubclass(Derived, HookedBase)
assert issubclass(Derived, object)

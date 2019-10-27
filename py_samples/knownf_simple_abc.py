# Derived from abc library documentation.


from abc import ABC


class CustomABC(ABC):
    pass


CustomABC.register(tuple)


assert issubclass(tuple, CustomABC)
assert isinstance((), CustomABC)

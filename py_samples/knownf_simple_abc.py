# Derived from abc library documentation.
#
# Sample from the docs:
# https://docs.python.org/3/library/abc.html#abc.ABCMeta.register


from abc import ABC


class CustomABC(ABC):
    pass


CustomABC.register(tuple)


assert issubclass(tuple, CustomABC)
assert isinstance((), CustomABC)

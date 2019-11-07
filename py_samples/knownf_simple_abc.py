# Derived from abc library documentation.
#
# Sample from the docs:
# https://docs.python.org/3/library/abc.html#abc.ABCMeta.register


from abc import ABC


class CustomABC(ABC):
    pass


assert hasattr(ABC, '__new__')
assert hasattr(CustomABC, '__new__')


CustomABC.register(tuple)


assert issubclass(tuple, CustomABC)
assert isinstance((), CustomABC)

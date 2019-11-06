class Base:
    pass


class Derived1(Base):
    pass


class Derived2(Base):
    pass


class Derived3(Derived2):
    pass


assert issubclass(Base, Base)
assert issubclass(Derived1, Base)
assert not issubclass(Base, Derived1)
assert issubclass(Derived2, Base)
assert not issubclass(Base, Derived2)
assert issubclass(Derived3, Base)
assert not issubclass(Base, Derived3)
assert issubclass(Derived3, Derived2)

assert isinstance(Base, type)
assert isinstance(Derived1, type)
assert isinstance(Derived2, type)
assert isinstance(Derived3, type)

class Base:
    pass


class Derived(Base):
    pass


scs = Base.__subclasses__()
assert scs == [Derived], scs

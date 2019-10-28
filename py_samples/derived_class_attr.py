class Base:
    def __init__(self):
        self.attr = 77


class Derived(Base):
    pass


d = Derived()
assert hasattr(d, 'attr'), d
assert d.attr == 77, d.attr

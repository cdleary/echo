class Base:
    def __init__(self):
        assert type(self) is Derived, type(self)
        self.attr = 42


class Derived(Base):
    def __init__(self):
        assert type(self) is Derived
        s = super()
        print(s)
        print(s.__init__)
        s.__init__()
        self.other_attr = 64


d = Derived()
assert d.attr == 42
assert d.other_attr == 64

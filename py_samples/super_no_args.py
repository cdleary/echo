class Base:
    def __init__(self):
        self.attr = 42


class Derived(Base):
    def __init__(self):
        super().__init__()
        self.other_attr = 64


d = Derived()
assert d.attr == 42
assert d.other_attr == 64

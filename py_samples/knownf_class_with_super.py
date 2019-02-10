class Base:
    def __init__(self, base_stuff):
        self.base_stuff = base_stuff


class Derived(Base):
    def __init__(self, derived_stuff, base_stuff):
        super(Derived, self).__init__(base_stuff)
        self.derived_stuff = derived_stuff


d = Derived(42, 64)
assert d.derived_stuff == 42
assert d.base_stuff == 64

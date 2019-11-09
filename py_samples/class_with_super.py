class Base:
    def __init__(self, base_stuff):
        self.base_stuff = base_stuff


class Derived(Base):
    def __init__(self, derived_stuff, base_stuff):
        s = super(Derived, self)
        print('super:', s)
        s.__init__(base_stuff)
        self.derived_stuff = derived_stuff


def main():
    d = Derived(42, 64)
    assert d.derived_stuff == 42
    assert d.base_stuff == 64


if __name__ == '__main__':
    main()

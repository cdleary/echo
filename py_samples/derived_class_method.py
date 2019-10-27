class Base:
    def run(self):
        return 42


class Derived(Base):
    pass


d = Derived()
assert d.run() == 42, d.run()
assert hasattr(d, 'run'), d

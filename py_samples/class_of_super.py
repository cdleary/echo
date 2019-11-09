class Base:
    pass


class Derived(Base):
    def __init__(self):
        print(super().__class__)


d = Derived()

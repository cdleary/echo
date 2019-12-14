class MyMeta(type):
    def f(cls): return cls.value


class Base(metaclass=MyMeta):
    value = 64


class Derived(Base):
    value = 42


assert type(Base) is MyMeta
assert type(Derived) is MyMeta
assert Base.f() == 64, Base.f()
assert Derived.f() == 42, Derived.f()

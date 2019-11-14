class MyMeta(type):
    def f(cls): return cls.value


class Base(metaclass=MyMeta):
    value = 64


class Derived(Base):
    value = 42


assert Base.f() == 64
assert Derived.f() == 42

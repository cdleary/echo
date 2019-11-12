class Base:
    def f(self): return 'Base'


class Derived(Base):
    def f(self): return 'Derived'


class Leaf(Derived):
    def f(self): return 'Leaf'


o = Leaf()
assert o.f() == 'Leaf'
assert super(Leaf, o).f() == 'Derived'
assert super(Derived, o).f() == 'Base'

#print("Leaf super's f:", super(Leaf, Leaf).f)

assert super(Leaf, Leaf).f is Derived.f, super(Leaf, Leaf).f 
assert super(Derived, Leaf).f is Base.f

assert super(Base, Leaf).__thisclass__ is Base
assert super(Base, Leaf).__self_class__ is Leaf
assert super(Base, Leaf).__self__ is Leaf

try:
    super(Base, Leaf).f  # Should try to resolve f on 'object'.
except AttributeError as e:
    assert "'super' object has no attribute 'f'" in str(e)
else:
    assert False

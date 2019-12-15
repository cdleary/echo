class Foo:
    @property
    def attr(self): raise ValueError

    @property
    def other(self): raise AttributeError


assert isinstance(Foo.attr, property)
assert isinstance(Foo.other, property)


assert hasattr(Foo, 'attr')
assert hasattr(Foo, 'other')


o = Foo()
assert not hasattr(o, 'other')

try:
    assert hasattr(o, 'attr')
except ValueError as e:
    pass  # Ok.
else:
    assert False

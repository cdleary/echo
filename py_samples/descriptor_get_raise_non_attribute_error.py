class Foo:
    @property
    def attr(self): raise ValueError


assert hasattr(Foo, 'attr')

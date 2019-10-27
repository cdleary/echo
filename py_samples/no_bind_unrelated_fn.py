class SomeClass:
    def __init__(self, f):
        self.f = f

    def g(self, x):
        return x

    def do_call(self, x):
        f = self.f
        g = self.g
        print('f:', f)
        print('g:', g)
        return g(f(x))


assert SomeClass(lambda x: x).do_call(42) == 42

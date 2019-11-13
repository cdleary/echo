class MyClass:
    def __init__(self, f):
        self.f = f


@MyClass
def f(x): return x


assert isinstance(f, MyClass), f

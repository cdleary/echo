class Foo:
    def __init__(self, value):
        self.value = value

    def __lt__(self, other):
        return self.value < other.value


f42 = Foo(42)
f64 = Foo(64)

assert f42 < f64
assert (f64 < f42) is False  # noqa

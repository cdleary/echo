class Overloader:
    def __init__(self, wrapped: int):
        assert isinstance(wrapped, int), wrapped
        self.wrapped = wrapped

    def __add__(self, other: 'Overloader') -> 'Overloader':
        return Overloader(self.wrapped + other.wrapped)

    def __eq__(self, other: 'Overloader') -> bool:
        return self.wrapped == other.wrapped


o = Overloader(42)
p = Overloader(24)
assert o + p == Overloader(42+24)
assert o + p is not Overloader(42+24)
assert o is o

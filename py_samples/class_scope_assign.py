class Subable:
    def __init__(self, value):
        self.value = value

    def difference(self, other):
        return Subable(self.value - other.value)

    __sub__ = difference


a = Subable(64)
b = Subable(42)
c = a - b
assert c.value == 22

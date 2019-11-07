news = []
inits = []


class MyClass:
    def __new__(cls, x, y):
        news.append((x, y))
        return None

    def __init__(self, x, y):
        inits.append(x, y)


o = MyClass(42, 24)
assert o is None
assert news == [(42, 24)]
assert inits == []

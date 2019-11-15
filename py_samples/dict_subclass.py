class MyDict(dict): pass


d = MyDict()
d.update(dict(k=42))
assert d == {'k': 42}

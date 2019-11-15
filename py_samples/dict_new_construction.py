new = dict.__new__
print(new)
d = new(dict)
assert isinstance(d, dict), d

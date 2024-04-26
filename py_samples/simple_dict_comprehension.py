items = 'o ok yah good'.split()
c = {p: len(p) for p in items}
print(c)
assert c == {'o': 1, 'ok': 2, 'yah': 3, 'good': 4}

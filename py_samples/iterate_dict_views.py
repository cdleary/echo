d = dict(a=77, b=42, c=64)

for k, v, i in zip(d.keys(), d.values(), d.items()):
    assert (k, v) == i, (k, v, i)

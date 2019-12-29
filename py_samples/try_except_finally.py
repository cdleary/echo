path = []
try:
    path.append(0)
    raise ValueError
except ValueError:
    path.append(1)
finally:
    path.append(2)
path.append(3)

assert path == [0, 1, 2, 3]

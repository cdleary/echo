def raiser():
    raise ValueError


try:
    raiser()
except ValueError:
    x = 42
else:
    x = 64

assert x == 42

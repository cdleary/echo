class MyException(Exception): pass

try:
    msg = 'oh no!'
    raise MyException(msg)
except MyException:
    x = 42
    y = 64

assert x == 42
assert y == 64

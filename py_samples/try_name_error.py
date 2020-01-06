try:
    foo
except NameError:
    foo = 42

assert foo == 42, foo

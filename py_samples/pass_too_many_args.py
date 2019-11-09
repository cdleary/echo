def f():
    pass


try:
    f(42)
except TypeError as e:
    print(str(e))
    assert str(e) == 'f() takes 0 positional arguments but 1 was given'
else:
    assert False

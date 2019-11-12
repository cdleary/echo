def f(a):
    return (a,)


try:
    f()
except TypeError as e:
    print(str(e))
    assert str(e) == \
        "f() missing 1 required positional argument: 'a'", str(e)
else:
    assert False

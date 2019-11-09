def f(a, b, c, d, e):
    return (a, b, c, d, e)


try:
    f(42)
except TypeError as e:
    print(str(e))
    assert str(e) == \
        "f() missing 4 required positional arguments: 'b', 'c', 'd', and 'e'"
else:
    assert False

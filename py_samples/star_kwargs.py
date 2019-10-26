def f(**kwargs):
    return kwargs

assert f(x=2, y=3) == dict(x=2, y=3)

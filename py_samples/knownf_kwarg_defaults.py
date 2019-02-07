def foo(x, *, y=2, z=3):
    return x+y+z


assert foo(1) == 6

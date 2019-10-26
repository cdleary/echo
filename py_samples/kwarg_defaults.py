# Uses keyword-only parameters.


def foo(x, *, y=2, z=3):
    return x+y+z


assert foo(1) == 6
assert foo(1, y=3) == 7
assert foo(1, z=5, y=3) == 9
assert foo(1, z=5) == 8

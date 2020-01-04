def foo(x, y=42, *, z=64):
    return x + y + z


assert foo(0) == 0+42+64

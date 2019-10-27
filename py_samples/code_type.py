def foo():
    return 42


def bar():
    return 77


assert type(foo.__code__) is type(bar.__code__)  # noqa

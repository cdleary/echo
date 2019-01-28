value = 42


def _ostensibly_private_func():
    return value


def inner_func():
    return _ostensibly_private_func()

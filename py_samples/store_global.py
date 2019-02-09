x = None


def store_global_helper():
    global x
    x = 42


store_global_helper()
assert x == 42

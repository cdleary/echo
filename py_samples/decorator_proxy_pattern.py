saw_invocation = False


def decorate(f):
    def wrapper(*args, **kwargs):
        global saw_invocation
        saw_invocation = True
        return f(*args, **kwargs)
    return wrapper


@decorate
def foo(bar, baz=True):
    return (bar, baz)


r = foo(baz=False, bar=42)
assert r == (42, False), r
assert saw_invocation, 'Did not see invocation'

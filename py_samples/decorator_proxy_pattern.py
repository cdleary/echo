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


assert foo(baz=False, bar=42) == (42, False)
assert saw_invocation

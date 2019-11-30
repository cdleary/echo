def foo(*, rkwo):
    return rkwo


try:
    foo(42)
except TypeError as e:
    assert 'foo() takes 0 positional arguments but 1 was given' == str(e), e
else:
    assert False

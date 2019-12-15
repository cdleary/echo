class MyException(Exception):
    pass


e = MyException()
try:
    raise e
except MyException as f:
    assert e is f
else:
    assert False

import sys

def f():
    assert isinstance(sys.exc_info()[1], ValueError), sys.exc_info()

    try:
        raise TypeError
    except TypeError:
        assert isinstance(sys.exc_info()[1], TypeError), sys.exc_info()

    assert isinstance(sys.exc_info()[1], ValueError), sys.exc_info()

def main():
    try:
        raise ValueError('here goes')
    finally:
        assert isinstance(sys.exc_info()[1], ValueError), sys.exc_info()
        f()
        assert isinstance(sys.exc_info()[1], ValueError), sys.exc_info()

assert sys.exc_info() == (None, None, None)

try:
    main()
except ValueError as e:
    assert e.args == ('here goes',)
else:
    assert False

assert sys.exc_info() == (None, None, None)

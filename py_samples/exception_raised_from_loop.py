def f():
    for i in range(2):
        raise ValueError(i)


def main():
    try:
        f()
    except ValueError as e:
        assert e.args[0] == 0
    else:
        raise AssertionError


main()

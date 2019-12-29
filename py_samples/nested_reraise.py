def f():
    try:
        raise TypeError('gets to the end')
    except TypeError:  # Handling type error.

        try:
            raise ValueError
        except ValueError:  # Handling value error in the type error.
            pass

        raise  # Re-raise the type error.


def main():
    try:
        raise ValueError("let's go")
    except ValueError:
        f()


try:
    main()
except TypeError as e:
    assert e.args[0] == 'gets to the end'

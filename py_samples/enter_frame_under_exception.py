called_f = False

def f(e):
    global called_f
    called_f = True
    assert isinstance(e, ValueError), e

def main():
    try:
        raise ValueError
    except ValueError as e:
        g = e
    finally:
        f(g)


main()
assert called_f

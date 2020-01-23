from echo.cg import longobject


def test_long_eq():
    f = longobject.make_long_eq()
    assert f(42, 42) is True
    assert f(1, 2) is False
    assert f(1, -1) is False
    assert f(-1, -1) is True
    assert f(1 << 29, 1 << 29) is True
    assert f(1 << 29, 1 << 30) is False
    assert f(1 << 30, 1 << 30) is True
    assert f(1 << 31, 1 << 30) is False
    assert f(-(1 << 30), 1 << 30) is False


def test_long_add():
    f = longobject.make_long_add()
    assert f(2, 2) == 4
    assert f(2, 3) == 5
    assert f(3, 2) == 5

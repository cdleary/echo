from echo.guest_objects import EClass


def test_subtype():
    base = EClass('Base', {})
    derived = EClass('Derived', {}, bases=(base,))

    assert derived.is_subtype_of(derived)
    assert base.is_subtype_of(base)
    assert derived.is_subtype_of(base)
    assert not base.is_subtype_of(derived)

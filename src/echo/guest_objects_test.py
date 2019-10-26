from echo.guest_objects import GuestClass


def test_subtype():
    base = GuestClass('Base', {})
    derived = GuestClass('Derived', {}, bases=(base,))

    assert derived.is_subtype_of(derived)
    assert base.is_subtype_of(base)
    assert derived.is_subtype_of(base)
    assert not base.is_subtype_of(derived)

from interp_routines import exception_match


def test_exception_match():
    assert exception_match(AssertionError, AssertionError)

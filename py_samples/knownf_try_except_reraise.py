try:
    try:  # Access a property on None.
        None.dne
    except AttributeError as fe:  # We should get an AttributeError for it.
        assert 'dne' in str(fe), fe
        print('ok so far...')
        raise
except AttributeError as e:  # We should catch the other attribute error we raised.
    assert 'dne' in str(e), e  # It should have the message we expected.
    # And now it should be implicitly squashed.

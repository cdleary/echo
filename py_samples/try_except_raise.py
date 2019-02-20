try:
    try:
        None.dne
    except AttributeError as fe:
        print(globals())
        assert 'dne' in str(fe), fe
        print('ok so far...')
        raise AttributeError('I like this message better')
except AttributeError as e:
    print(globals())
    assert 'better' in str(e), e

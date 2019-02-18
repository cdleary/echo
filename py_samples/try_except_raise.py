try:
    try:
        None.dne
    except AttributeError as fe:
        assert 'dne' in str(fe)
        print('ok so far...')
        raise AttributeError('I like this message better')
except AttributeError as e:
    print(globals())
    print('even closer...')
    assert 'better' in str(e), e

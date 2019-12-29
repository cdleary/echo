import sys

try:
    try:
        None.dne
    except AttributeError as fe:
        assert 'dne' in str(fe), fe
        print('ok so far...', file=sys.stderr)
        raise AttributeError('I like this message better')
except AttributeError as e:
    assert 'better' in str(e), e

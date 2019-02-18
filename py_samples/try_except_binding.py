try:
    None.dne
except AttributeError as e:
    assert 'dne' in str(e)

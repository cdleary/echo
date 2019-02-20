try:
    None.dne
except AttributeError as e:
    assert isinstance(e, AttributeError)

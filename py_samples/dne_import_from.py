try:
    from sys import shoobadooba
except ImportError as e:
    assert repr(e) == """ImportError("cannot import name 'shoobadooba' from 'sys' (unknown location)")""", repr(e)
else:
    raise AssertionError

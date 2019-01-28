try:
    from does_not_exist import *
except ImportError:
    pass
else:
    assert False

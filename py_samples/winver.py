import sys

try:
    sys.getwindowsversion()
except (AttributeError, ImportError):
    pass
else:
    assert False

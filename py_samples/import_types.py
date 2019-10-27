import sys


# Python 3.6 imports collections.abc as part of types, but there is a separate
# test for abc.
if sys.version_info >= (3, 7):
    import types
else:
    print('Skipping types import for version:', sys.version_info)

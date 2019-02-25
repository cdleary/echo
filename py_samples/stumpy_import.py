import sys

import stumpy

assert stumpy.__name__ == 'stumpy', stumpy.__name__
assert 'stumpy' in sys.modules
assert 'stumpy.config' in sys.modules
assert stumpy.stumpy_show() == 42
assert stumpy.thing.f() == 64

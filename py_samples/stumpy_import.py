import os
import sys

import stumpy

dirpath = os.path.realpath(os.path.dirname(__file__))
assert stumpy.__name__ == 'stumpy', stumpy.__name__
want = [os.path.join(dirpath, 'stumpy')]
assert stumpy.__path__ == want, (stumpy.__path__, want)
assert 'stumpy' in sys.modules
assert 'stumpy.config' in sys.modules
assert stumpy.stumpy_show() == 42
assert stumpy.thing.f() == 64

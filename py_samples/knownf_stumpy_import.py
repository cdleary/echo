import os
import sys

modules_before = set(sys.modules.keys())

import stumpy  # nopep8: for testing purposes

modules_after = set(sys.modules.keys())

diff = modules_after-modules_before
assert diff == {
    'stumpy.config', 'stumpy._stuff.other_module', 'stumpy._stuff.thing',
    'stumpy._stuff', 'stumpy',
}, diff

dirpath = os.path.realpath(os.path.dirname(__file__))
assert dirpath.endswith('/py_samples'), dirpath

print('dirpath:', dirpath)

assert stumpy.__name__ == 'stumpy', stumpy.__name__
assert stumpy.config.__name__ == 'stumpy.config'
assert stumpy._stuff.__name__ == 'stumpy._stuff'
assert stumpy._stuff.thing.__name__ == 'stumpy._stuff.thing'
want = [os.path.join(dirpath, 'stumpy')]
assert stumpy.__path__ == want, \
    'Want {!r} got module __path__ {!r}'.format(want, stumpy.__path__)
assert 'stumpy' in sys.modules
assert 'stumpy.config' in sys.modules
assert stumpy.stumpy_show() == 42
assert stumpy.thing.f() == 64

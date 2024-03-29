import os
import sys

this_dir = os.path.dirname(__file__)
print('__file__:', __file__, file=sys.stderr)
print('this_dir:', this_dir, file=sys.stderr)
sys.path += [
    os.path.join(this_dir, 'foo/bar'),
    os.path.join(this_dir, 'foo'),
    this_dir,
]
print(sys.path, file=sys.stderr)

import counter  # nopep8: for testing purposes
import baz  # nopep8: for testing purposes
import bar.baz  # nopep8: for testing purposes
import foo.bar.baz  # nopep8: for testing purposes


assert counter.count == 3
print([name for name in sys.modules.keys() if 'baz' in name], file=sys.stderr)

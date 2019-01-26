import os
import sys

import pytest

import interp


SAMPLE_DIR = 'py_samples'
SAMPLE_FILES = [os.path.join(SAMPLE_DIR, p) for p in os.listdir(SAMPLE_DIR)
                if p.endswith('.py')]


@pytest.mark.parametrize('path', SAMPLE_FILES)
def test_echo_on_sample(path):
    globals_ = dict(globals())
    globals_['__file__'] = path
    sys.path[0] = os.path.dirname(path)
    interp.import_path(path)

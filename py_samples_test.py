import os
import sys

import pytest

import interp


SAMPLE_DIR = 'py_samples'
SAMPLE_FILES = [os.path.join(SAMPLE_DIR, p) for p in os.listdir(SAMPLE_DIR)
                if p.endswith('.py') and not p.startswith('noexec')]


@pytest.mark.parametrize('path', SAMPLE_FILES)
def test_echo_on_sample(path):
    basename = os.path.basename(path)
    if basename.startswith('knownf_'):
        pytest.xfail('Known-failing sample.')
    globals_ = dict(globals())
    globals_['__file__'] = path
    sys.path[0] = os.path.dirname(path)
    fully_qualified = '__main__'
    state = interp.InterpreterState()
    interp.import_path(path, fully_qualified, state)

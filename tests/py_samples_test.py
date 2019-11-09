import functools
import os
import pprint
import sys
from typing import Tuple, Any, Text

import pytest

from echo import interp


SAMPLE_DIR = 'py_samples'
SAMPLE_FILES = [os.path.join(SAMPLE_DIR, p) for p in os.listdir(SAMPLE_DIR)
                if p.endswith('.py') and not p.startswith('noexec')]


def _version_to_tuple(s: Text) -> Tuple[int, ...]:
    return tuple(int(x) for x in s.split('.'))


def test_version_to_tuple():
    assert _version_to_tuple('3.7') == (3, 7)


def _is_prefix_of(xs: Tuple[Any, ...], ys: Tuple[Any, ...]) -> bool:
    return all(x == y for x, y in zip(xs, ys))


def test_is_prefix_of():
    assert _is_prefix_of((3, 7), (3, 7, 2))


@pytest.mark.parametrize('path', SAMPLE_FILES)
def test_echo_on_sample(path: Text):
    basename = os.path.basename(path)
    if basename.startswith('knownf_'):
        pytest.xfail('Known-failing sample.')
    with open(path) as f:
        contents = f.read()
    leader = '# knownf: '
    if contents.startswith(leader):
        line0 = contents.splitlines()[0]
        versions = [_version_to_tuple(x)
                    for x in line0[len(leader):].split(', ')]
        for version in versions:
            if _is_prefix_of(version, sys.version_info):
                pytest.xfail('Version marked as known-failing.')
    globals_ = dict(globals())
    fullpath = os.path.realpath(path)
    globals_['__file__'] = fullpath
    fully_qualified_name = '__main__'
    state = interp.InterpreterState(os.path.dirname(fullpath))
    state.paths += sys.path[1:]
    result = interp.import_path(path, fully_qualified_name,
                                fully_qualified_name, state)
    if result.is_exception():
        print(result.get_exception().exception)
        pprint.pprint(result.get_exception().traceback, width=120)
    assert not result.is_exception(), result.get_exception()

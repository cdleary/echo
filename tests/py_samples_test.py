import functools
import itertools
import os
import pprint
import subprocess as subp
import sys
from typing import Tuple, Any, Text

import pytest

from echo import interp
from echo import interp_result
from echo import interp_context


SAMPLE_DIR = 'py_samples'
SAMPLE_FILES = [os.path.join(SAMPLE_DIR, p) for p in os.listdir(SAMPLE_DIR)
                if p.endswith('.py') and not p.startswith('noexec')]
EVM_FAILING_SAMPLES = [
    'bad_class_kwarg',
    'import_numpy',
    'prepare_hook_user_type',
    'simple_class_repr',
    'simple_repr_udt',
    'type_subclass_of_abc',
    'import_textwrap',
]


def _version_to_tuple(s: Text) -> Tuple[int, ...]:
    return tuple(int(x) for x in s.split('.'))


def test_version_to_tuple() -> None:
    assert _version_to_tuple('3.7') == (3, 7)


def _is_prefix_of(xs: Tuple[Any, ...], ys: Tuple[Any, ...]) -> bool:
    return all(x == y for x, y in zip(xs, ys))


def test_is_prefix_of() -> None:
    assert _is_prefix_of((3, 7), (3, 7, 2))


def run_to_result(path: Text, vm: Text) -> interp_result.Result[Any]:
    basename = os.path.basename(path)
    fullpath = os.path.realpath(path)
    dirpath = os.path.dirname(fullpath)

    if vm == 'cpy':
        subp.check_call(['python', path])
        return interp_result.Result(None)

    if basename.startswith('knownf_'):
        pytest.xfail('Known-failing sample.')

    if os.path.splitext(basename)[0] in EVM_FAILING_SAMPLES:
        pytest.xfail('Known-failing echo VM sample.')

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
    globals_['__file__'] = fullpath
    fully_qualified_name = '__main__'
    state = interp.InterpreterState(dirpath)
    state.paths += sys.path[1:]

    ictx = interp_context.ICtx(state, interp.interp, interp.do_call)

    result = interp.import_path(path, fully_qualified_name,
                                fully_qualified_name, ictx)
    if result.is_exception():
        print(result.get_exception().exception)
        pprint.pprint(result.get_exception().traceback, width=120)
    return result


PROD = itertools.product(('evm', 'cpy'), SAMPLE_FILES)


@pytest.mark.parametrize('vm,path', PROD)
def test_echo_on_sample(path: Text, vm: Text):
    r = run_to_result(path, vm)
    assert not r.is_exception(), r.get_exception()

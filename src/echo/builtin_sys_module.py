import sys
from typing import Tuple, Dict, Any, Text, Callable

from echo.eobjects import NativeFunction, get_guest_builtin
from echo.emodule import EModule
from echo.interp_result import Result, ExceptionData
from echo.interp_context import ICtx


SPECIAL_MODULES = (
    'itertools', 'time', 'ctypes', 'subprocess', 'shutil', 'posix', 'errno',

    # _ prefixed modules.
    '_collections', '_signal', '_stat', '_weakref', '_weakrefset', '_thread',
    '_sre', '_struct', '_codecs', '_pickle', '_ast', '_io', '_functools',
    '_warnings',
)


def _get_exc_info(
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    exc_info = ictx.exc_info
    if not exc_info:
        return Result((None, None, None))
    do_type = get_guest_builtin('type')
    exc_type = do_type.invoke((exc_info.exception,), {}, {}, ictx).get_value()
    return Result((exc_type, exc_info.exception, exc_info.traceback))


def wrap_sys(name: Text, arity: int) -> Callable:
    sys_f = getattr(sys, name)

    def f(args: Tuple[Any, ...],
          kwargs: Dict[Text, Any],
          locals_dict: Dict[Text, Any],
          ictx: ICtx) -> Result[Any]:
        assert len(args) == arity and not kwargs
        return Result(sys_f(*args))
    return NativeFunction(f, f'sys.{name}')


def make_sys_module() -> EModule:
    globals_ = dict(
        stdout=sys.stdout,
        stderr=sys.stderr,
        warnoptions=[],
        implementation=sys.implementation,
        exc_info=NativeFunction(_get_exc_info, 'sys.exc_info'),
        intern=wrap_sys('intern', 1),
        getfilesystemencoding=wrap_sys('getfilesystemencoding', 0),
        getfilesystemencodeerrors=wrap_sys('getfilesystemencodeerrors', 0),
        builtin_module_names=SPECIAL_MODULES,
        maxsize=sys.maxsize,
        platform=sys.platform,
        version_info=sys.version_info,
        version=sys.version,
        byteorder=sys.byteorder,
        executable=sys.executable,
    )

    def _set_paths(v, ictx) -> Result[None]:
        assert isinstance(v, list), v
        ictx.interp_state.paths = v
        return Result(None)

    return EModule(
        'sys', filename='<built-in>', globals_=globals_,
        special_attrs={
            'modules': ((lambda ictx: Result(ictx.interp_state.sys_modules)),
                        None),
            'path': ((lambda ictx: Result(ictx.interp_state.paths)),
                     _set_paths),
        },
    )

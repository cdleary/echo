from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
    do_iter, do_next,
)
from echo.interp_context import ICtx


@register_builtin('tuple')
@check_result
def _do_tuple(args: Tuple[Any, ...],
              kwargs: Dict[Text, Any],
              ictx: ICtx) -> Result[Any]:
    assert isinstance(args, tuple), args
    if len(args) == 1 and isinstance(args[0], EPyObject):
        it = args[0]
        items = []
        while True:
            r = do_next((it,))
            if (r.is_exception() and
                    isinstance(r.get_exception().exception, StopIteration)):
                break
            if r.is_exception():
                return r
            items.append(r.get_value())

        return Result(tuple(items))

    return Result(tuple(*args, **kwargs))

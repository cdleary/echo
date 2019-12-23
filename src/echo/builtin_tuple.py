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
from echo import iteration_helpers


@register_builtin('tuple')
@register_builtin('tuple.__new__')
@check_result
def _do_tuple(args: Tuple[Any, ...],
              kwargs: Dict[Text, Any],
              ictx: ICtx) -> Result[Any]:
    assert isinstance(args, tuple), args
    if len(args) == 1 and isinstance(args[0], EPyObject):
        it = args[0]
        items = []

        def cb(item) -> Result[bool]:
            items.append(item)
            return Result(True)

        res = iteration_helpers.foreach(it, cb, ictx)
        if res.is_exception():
            return res

        return Result(tuple(items))

    return Result(tuple(*args, **kwargs))

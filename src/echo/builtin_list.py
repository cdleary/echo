from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


@register_builtin('list')
@check_result
def _do_list(args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    if isinstance(args[0], EPyObject):
        if args[0].get_type() == get_guest_builtin('map'):
            result = []
            for e in args[0].it:
                r = args[0].f.invoke((e,), {}, {}, ictx)
                if r.is_exception():
                    return r
                result.append(r.get_value())
            return Result(result)
        if hasattr(args[0], 'next'):
            result = []
            while True:
                r = args[0].next()
                if (r.is_exception() and isinstance(
                        r.get_exception().exception, StopIteration)):
                    break
                if r.is_exception():
                    return r
                result.append(r.get_value())
            return Result(result)

    return Result(list(*args, **kwargs))

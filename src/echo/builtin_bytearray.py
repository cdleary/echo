from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx
from echo import iteration_helpers


@register_builtin('bytearray')
@check_result
def _do_bytearray_call(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(bytearray(*args))


@register_builtin('bytearray.__setitem__')
@check_result
def _do_bytearray_setitem(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 3 and not kwargs
    ba, index, value = args
    assert isinstance(ba, bytearray), ba
    try:
        ba[index] = value
    except IndexError as e:
        return Result(ExceptionData(None, None, e))
    return Result(None)

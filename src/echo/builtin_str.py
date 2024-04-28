from typing import Text, Tuple, Any, Dict, Optional, List

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
from echo.value import Value


@register_builtin('str')
@check_result
def _do_str_call(args: Tuple[Any, ...],
                 kwargs: Dict[Text, Any], ictx: ICtx) -> Result[Any]:
    assert 1 <= len(args) <= 2 and not kwargs, (args, kwargs)
    o = args[0]
    if not isinstance(o, EPyObject):
        return Result(str(*args))
    assert len(args) == 1
    fstr_ = o.getattr('__str__', ictx=ictx)
    if fstr_.is_exception():
        return fstr_
    fstr = fstr_.get_value()
    globals_ = fstr.getattr('__globals__', ictx=ictx)
    return ictx.call(fstr, args=(), kwargs={}, locals_dict={},
                     globals_=globals_)


@register_builtin('str.join')
@check_result
def _do_str_join(args: Tuple[Any, ...],
                 kwargs: Dict[Text, Any], ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    joiner, it = args
    assert isinstance(joiner, str), joiner
    do_str = get_guest_builtin('str')
    pieces: List[str] = []

    def cb(item: Any) -> Result[bool]:
        assert isinstance(item, str), item
        res = do_str.invoke((item,), {}, {}, ictx)
        if res.is_exception():
            return res
        assert isinstance(res.get_value(), str), res
        if pieces:
            pieces.append(joiner)
        pieces.append(res.get_value())
        return Result(True)

    res = iteration_helpers.foreach(it, cb, ictx)
    if res.is_exception():
        return res

    return Result(''.join(pieces))

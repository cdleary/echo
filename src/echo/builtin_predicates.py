from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx
from echo import iteration_helpers


@register_builtin('bool')
@check_result
def _do_bool_call(args: Tuple[Any, ...],
                  kwargs: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs
    o = args[0]
    if not isinstance(o, EPyObject):
        assert isinstance(o, (int, bool, str, set, tuple, dict, list,
                              type(None))), o
        return Result(bool(o))
    if isinstance(o, EBuiltin):
        log('fo:truthy', f'builtin o: {o}')
        return Result(True)
    raise NotImplementedError(o)


@register_builtin('any')
@check_result
def _do_any(args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args

    found = False
    do_bool = get_guest_builtin('bool')

    def callback(item) -> Result[bool]:
        res = do_bool.invoke((item,), {}, {}, ictx)
        if res.is_exception:
            return res
        b = res.get_value()
        assert isinstance(b, bool), b
        return Result(b)

    res = iteration_helpers.foreach(args[0], callback, ictx)
    if res.is_exception():
        return res

    return Result(found)


@register_builtin('callable')
@check_result
def _do_callable(args: Tuple[Any, ...],
                 kwargs: Dict[Text, Any],
                 ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    o = args[0]
    if not isinstance(o, EPyObject):
        return Result(callable(o))
    do_hasattr = get_guest_builtin('hasattr')
    return do_hasattr.invoke((o, '__call__'), {}, {}, ictx)

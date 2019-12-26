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
    if isinstance(o, EPyObject):
        if o.get_type().hasattr('__bool__'):
            f = o.getattr('__bool__', ictx)
            if f.is_exception():
                return f
            f = f.get_value()
            return f.invoke((), {}, {}, ictx)

        do_len = get_guest_builtin('len')
        res = do_len.invoke((o,), {}, {}, ictx)
        if res.is_exception():
            return res
        v = res.get_value()
        return Result(bool(v))

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


@register_builtin('min')
@check_result
def _do_min(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    if (not isinstance(args[0], EPyObject) and
            not isinstance(args[1], EPyObject)):
        return Result(min(args[0], args[1]))
    do_getattr = get_guest_builtin('getattr')
    do_lt = do_getattr.invoke((args[0], '__lt__',), {}, {}, ictx)
    if do_lt.is_exception():
        return do_lt
    do_lt = do_lt.get_value()
    res = do_lt.invoke((args[1],), {}, {}, ictx)
    if res.is_exception():
        return res
    return Result(args[0] if res.get_value() else args[1])


@register_builtin('max')
@check_result
def _do_max(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    if (not isinstance(args[0], EPyObject) and
            not isinstance(args[1], EPyObject)):
        return Result(max(args[0], args[1]))
    do_getattr = get_guest_builtin('getattr')
    do_lt = do_getattr.invoke((args[0], '__lt__',), {}, {}, ictx)
    if do_lt.is_exception():
        return do_lt
    do_lt = do_lt.get_value()
    res = do_lt.invoke((args[1],), {}, {}, ictx)
    if res.is_exception():
        return res
    return Result(args[1] if res.get_value() else args[0])

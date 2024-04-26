import collections
import re
import types
from typing import Text, Tuple, Any, Dict, Optional

import io
import _thread

from echo.elog import log
from echo.epy_object import EPyObject, AttrWhere, try_invoke
from echo.interp_result import Result, check_result, ExceptionData
from echo import interp_routines
from echo.eobjects import (
    EFunction, EBuiltin, EClass, EInstance,
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
                              collections.deque, types.FunctionType,
                              types.MethodType, types.BuiltinMethodType,
                              types.BuiltinFunctionType,
                              types.MethodDescriptorType,
                              getattr(_thread, 'RLock'), io.TextIOBase,
                              type(None), getattr(re, 'Match'))), \
            (o, type(o))
        return Result(bool(o))
    if isinstance(o, EBuiltin):
        log('fo:truthy', f'builtin o: {o}')
        return Result(True)
    if isinstance(o, EPyObject):
        if o.get_type().hasattr('__bool__'):
            f_ = o.getattr('__bool__', ictx)
            if f_.is_exception():
                return f_
            f = f_.get_value()
            return f.invoke((), {}, {}, ictx)

        if o.get_type().hasattr('__len__'):
            do_len = get_guest_builtin('len')
            res = do_len.invoke((o,), {}, {}, ictx)
            if res.is_exception():
                return res
            v = res.get_value()
            return Result(bool(v))

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
        if res.is_exception():
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
    do_lt_ = do_getattr.invoke((args[0], '__lt__',), {}, {}, ictx)
    if do_lt_.is_exception():
        return do_lt_
    do_lt = do_lt_.get_value()
    res = do_lt.invoke((args[1],), {}, {}, ictx)
    if res.is_exception():
        return res
    return Result(args[0] if res.get_value() else args[1])


def _do_max_iterable(iterable: Any, ictx: ICtx) -> Result[Any]:
    sentinel = object()
    accum = sentinel
    do_max = get_guest_builtin('max')

    def cb(o) -> Result[bool]:
        nonlocal accum
        if accum is sentinel:
            accum = o
        else:
            res = do_max.invoke((accum, o), {}, {}, ictx)
            if res.is_exception():
                return res
            accum = res.get_value()
        return Result(True)

    res = iteration_helpers.foreach(iterable, cb, ictx)
    if res.is_exception():
        return res

    if accum is sentinel:
        return Result(ExceptionData(
            None, None, ValueError('max() arg is an empty sequence')))

    return Result(accum)


@register_builtin('max')
@check_result
def _do_max(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    if len(args) == 1:
        assert not kwargs
        return _do_max_iterable(args[0], ictx)

    if (not isinstance(args[0], EPyObject) and
            not isinstance(args[1], EPyObject)):
        return Result(max(args[0], args[1]))
    do_getattr = get_guest_builtin('getattr')
    do_lt = do_getattr.invoke((args[0], '__lt__',), {}, {}, ictx)
    if do_lt.is_exception():
        return do_lt
    do_lt = do_lt.get_value()
    assert isinstance(do_lt, EPyObject), do_lt
    res = try_invoke(do_lt, (args[1],), {}, {}, ictx)
    if res.is_exception():
        return res
    return Result(args[1] if res.get_value() else args[0])


@register_builtin('sum')
@check_result
def _do_sum(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert 1 <= len(args) <= 2 and not kwargs

    accum = 0 if len(args) == 1 else args[2]

    def callback(item) -> Result[bool]:
        nonlocal accum
        add_res = item.getattr('__add__', ictx)
        if add_res.is_exception():
            return add_res
        f = add_res.get_value()
        res = f.invoke((accum,), {}, {}, ictx)
        if res.is_exception():
            return res
        accum = res.get_value()
        return Result(True)

    res = iteration_helpers.foreach(args[0], callback, ictx)
    if res.is_exception():
        return res

    return Result(accum)

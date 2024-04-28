from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EBuiltin, EClass, EInstance,
    register_builtin, is_tuple_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx
from echo import iteration_helpers


@register_builtin('tuple')
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


@register_builtin('tuple.__new__')
@check_result
def _do_tuple_new(args: Tuple[Any, ...],
                  kwargs: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
    assert 1 <= len(args) <= 2 and not kwargs, (args, kwargs)
    do_tuple = get_guest_builtin('tuple')
    data = ()
    if len(args) == 2:
        res = do_tuple.invoke((args[1],), {}, {}, ictx)
        if res.is_exception():
            return res
        data = res.get_value()
    if isinstance(args[0], EClass):
        inst = EInstance(args[0])
        inst.builtin_storage[tuple] = data
        return Result(inst)
    if is_tuple_builtin(args[0]):
        return Result(data)
    raise NotImplementedError(args, kwargs)


@register_builtin('tuple.__init__')
@check_result
def _do_tuple_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(None)


def _resolve(x: Any) -> Tuple:
    if isinstance(x, EInstance):
        return x.builtin_storage[tuple]
    if isinstance(x, tuple):
        return x
    # Raise type error.
    raise NotImplementedError(x)


@register_builtin('tuple.__eq__')
@check_result
def _do_tuple_eq(args: Tuple[Any, ...],
                 kwargs: Dict[Text, Any],
                 ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    return Result(_resolve(args[0]) == _resolve(args[1]))


@register_builtin('tuple.__lt__')
@check_result
def _do_tuple_lt(args: Tuple[Any, ...],
                 kwargs: Dict[Text, Any],
                 ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    return Result(_resolve(args[0]) < _resolve(args[1]))


@register_builtin('tuple.__getitem__')
@check_result
def _do_tuple_getitem(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    return Result(_resolve(args[0])[args[1]])

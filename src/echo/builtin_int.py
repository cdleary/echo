from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, check_result, ExceptionData
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


def _resolve(x: Any) -> int:
    if isinstance(x, EPyObject):
        return x.builtin_storage[int]
    if isinstance(x, int):
        return x
    # Raise type error.
    raise NotImplementedError(x)


@register_builtin('int')
@check_result
def _do_int(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    try:
        return Result(int(*args, **kwargs))
    except ValueError as e:
        return Result(ExceptionData(None, None, e))


@register_builtin('int.__new__')
@check_result
def _do_int_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert 1 <= len(args) <= 2
    cls = args[0]
    value = args[1] if len(args) > 1 else 0
    if isinstance(cls, EClass):
        assert get_guest_builtin('int') in cls.get_mro()
        globals_ = {}
        o = EInstance(cls)
        o.builtin_storage[int] = value
        return Result(o)
    raise NotImplementedError(args, kwargs)


@register_builtin('int.__add__')
@check_result
def _do_int_add(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    assert not kwargs
    assert isinstance(args[1], int)  # TODO
    return Result(_resolve(args[0]) + args[1])

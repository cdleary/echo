from typing import Text, Tuple, Any, Dict, Optional
import operator

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
    assert len(args) == 1 and not kwargs, (args, kwargs)
    if isinstance(args[0], EPyObject):
        int_res = args[0].getattr('__int__', ictx)
        if int_res.is_exception():
            return int_res
        return int_res.get_value().invoke((), {}, {}, ictx)
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


@register_builtin('int.__init__')
@check_result
def _do_int_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(None)


@register_builtin('int.__add__')
@check_result
def _do_int_add(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    assert not kwargs
    assert isinstance(args[1], int)  # TODO
    return Result(_resolve(args[0]) + _resolve(args[1]))


@register_builtin('int.__bool__')
@check_result
def _do_int_add(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    assert not kwargs
    return Result(bool(_resolve(args[0])))


@register_builtin('int.__rmul__')
@register_builtin('int.__mul__')
@check_result
def _do_int_mul(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    assert not kwargs
    assert isinstance(args[1], int)  # TODO
    return Result(_resolve(args[0]) * _resolve(args[1]))


@register_builtin('int.__sub__')
@check_result
def _do_int_sub(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    assert not kwargs
    assert isinstance(args[1], int)  # TODO
    return Result(_resolve(args[0]) - args[1])


@register_builtin('int.__rand__')
@register_builtin('int.__and__')
@check_result
def _do_int_and(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    assert not kwargs
    assert isinstance(args[1], int)  # TODO
    return Result(_resolve(args[0]) & args[1])


@register_builtin('int.__repr__')
@check_result
def _do_int_repr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    assert not kwargs
    return Result(repr(_resolve(args[0])))


@register_builtin('int.__str__')
@check_result
def _do_int_str(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    assert not kwargs
    return Result(str(_resolve(args[0])))


@register_builtin('int.__int__')
@check_result
def _do_int_str(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    assert not kwargs
    return Result(int(_resolve(args[0])))


_COMPARE_OP_DATA = [
    ('__eq__', operator.eq),
    ('__lt__', operator.lt),
    ('__ge__', operator.ge),
    ('__le__', operator.le),
    ('__gt__', operator.gt),
]


def _make_fcmp(name, op):
    def do_compare(
            args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            ictx: ICtx) -> Result[Any]:
        assert len(args) == 2, args
        assert not kwargs
        try:
            rhs = _resolve(args[1])
        except KeyError:
            return Result(NotImplemented)
        return Result(op(_resolve(args[0]), rhs))
    return do_compare


def _register_compare_ops():
    for name, op in _COMPARE_OP_DATA:
        f = _make_fcmp(name, op)
        register_builtin(f'int.{name}')(f)


_register_compare_ops()

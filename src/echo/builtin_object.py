from typing import Text, Tuple, Any, Dict

from echo.elog import log
from echo.interp_result import Result, check_result
from echo.eobjects import (
    EBuiltin, EClass, EInstance, register_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


@check_result
@register_builtin('object.__eq__')
def _do_object_eq(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert not kwargs
    assert len(args) == 2, args
    lhs, rhs = args
    return Result(NotImplemented)


@check_result
@register_builtin('object.__new__')
def _do_object_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    assert isinstance(args[0], (EClass, EBuiltin)), args
    return Result(EInstance(args[0]))


@check_result
@register_builtin('object.__init__')
def _do_object_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    assert isinstance(args[0], (EInstance)), args
    return Result(None)


@check_result
@register_builtin('object.__repr__')
def _do_object_repr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    raise NotImplementedError(args[0])


@check_result
@register_builtin('object.__ne__')
def _do_object_ne(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert not kwargs
    lhs, rhs = args
    return Result(NotImplemented)


@register_builtin('object')
@check_result
def _do_object(args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
    assert len(args) == 0, args
    return Result(EInstance(cls=get_guest_builtin('object')))


@register_builtin('object.__subclasshook__')
@check_result
def _do_object_subclasshook(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(NotImplemented)


@register_builtin('object.__setattr__')
@check_result
def _do_object_setattr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 3, args
    assert not kwargs
    o, name, value = args
    log('eo:object_setattr', f'o {o} name {name} value {value}')
    if isinstance(o, (EInstance, EClass)):
        o.dict_[name] = value
    else:
        raise NotImplementedError
    return Result(None)

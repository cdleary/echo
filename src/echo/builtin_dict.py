from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


@register_builtin('dict.__new__')
@check_result
def _do_dict_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    if isinstance(args[0], EClass):
        inst = EInstance(args[0])
        inst.builtin_storage[dict] = {}
        return Result(inst)
    if _is_dict_builtin(args[0]):
        return Result({})
    raise NotImplementedError(args, kwargs)


def _resolve(x: Any) -> Dict:
    if isinstance(x, EPyObject):
        return x.builtin_storage[dict]
    if isinstance(x, dict):
        return x
    # Raise type error.
    raise NotImplementedError(x)


@register_builtin('dict.__eq__')
@check_result
def _do_dict_eq(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    lhs, rhs = args
    lhs = _resolve(lhs)
    rhs = _resolve(rhs)
    if len(lhs) != len(rhs):
        return Result(False)
    for k in set(lhs.keys()) | set(rhs.keys()):
        if k not in lhs or k not in rhs:
            return Result(False)
        e_result = interp_routines.compare('==', lhs[k], rhs[k], ictx)
        if e_result.is_exception():
            return e_result
        if not e_result.get_value():
            return Result(False)
    return Result(True)


@register_builtin('dict')
@check_result
def _do_dict_call(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    d = dict(*args, **kwargs)
    log('go:dict()', f'dict(*{args}, **{kwargs}) => {d}')
    return Result(d)


@register_builtin('dict.__init__')
@register_builtin('dict.update')
@check_result
def _do_dict_update(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[None]:
    if len(args) <= 1 and not kwargs:
        return Result(None)
    log('go:dict.update', f'args: {args} kwargs: {kwargs}')
    if isinstance(args[0], EInstance):
        d = args[0].builtin_storage[dict]
    else:
        assert isinstance(args[0], dict), args
        d = args[0]
    d.update(*args[1:], **kwargs)
    log('go:dict.update', f'd after: {args[0]}')
    return Result(None)


@register_builtin('dict.__getitem__')
@check_result
def _do_dict_getitem(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[None]:
    lhs, rhs = args
    d = _resolve(lhs)
    return Result(d.__getitem__(rhs))


@register_builtin('dict.__setitem__')
@check_result
def _do_dict_setitem(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[None]:
    assert len(args) == 3, args
    assert not kwargs, kwargs
    lhs, k, v = args
    d = _resolve(lhs)
    return Result(d.__setitem__(k, v))


@register_builtin('dict.setdefault')
@check_result
def _do_dict_setdefault(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[None]:
    d = _resolve(args[0])
    r = d.setdefault(*args[1:], **kwargs)
    return Result(r)


@register_builtin('dict.__instancecheck__')
@check_result
def _do_dict_instancecheck(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    if isinstance(args[0], dict):
        return Result(True)
    if isinstance(args[0], EInstance):
        return Result(get_guest_builtin('dict') in args[0].get_mro())
    return Result(False)

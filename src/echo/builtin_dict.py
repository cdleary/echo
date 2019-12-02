from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
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
        return Result(EInstance(args[0]))
    if _is_dict_builtin(args[0]):
        return Result({})
    raise NotImplementedError(args, kwargs)


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
    log('go:dict.update', f'args: {args} kwargs: {kwargs}')
    assert isinstance(args[0], dict), args
    args[0].update(*args[1:], **kwargs)
    log('go:dict.update', f'd after: {args[0]}')
    return Result(None)


@register_builtin('dict.setdefault')
@check_result
def _do_dict_setdefault(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[None]:
    assert isinstance(args[0], dict), args
    r = args[0].setdefault(*args[1:], **kwargs)
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

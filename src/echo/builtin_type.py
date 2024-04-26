from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx
from echo.ebuiltins import TYPE_TO_EBUILTIN


@register_builtin('type.__new__')
@check_result
def _do_type_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[EClass]:
    if kwargs:
        kwarg_metaclass = kwargs.pop('metaclass', args[0])
        assert kwarg_metaclass is args[0]
        assert not kwargs, kwargs
    if len(args) != 4:
        msg = f"Expected 4 arguments to type.__new__, got {len(args)}"
        return Result(ExceptionData(
            None, None,
            TypeError(msg)))
    metaclass, name, bases, ns = args
    do_dict = get_guest_builtin('dict')
    ns_copy_ = do_dict.invoke((ns,), {}, {}, ictx)
    if ns_copy_.is_exception():
        return ns_copy_
    ns_copy = ns_copy_.get_value()
    assert isinstance(ns_copy, dict), ns_copy
    cls = EClass(name, dict_=ns_copy, bases=bases, metaclass=metaclass)
    return Result(cls)


@register_builtin('type.__init__')
@check_result
def _do_type_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(None)


@register_builtin('type.__str__')
@check_result
def _do_type_str(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    raise NotImplementedError(args)


@register_builtin('type.__repr__')
@check_result
def _do_type_repr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    return Result(repr(args[0]))


@register_builtin('type.mro')
@check_result
def _do_type_mro(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert isinstance(args, tuple), args
    assert len(args) == 1
    assert not kwargs
    if isinstance(args[0], EClass):
        return Result(list(args[0].get_mro()))
    else:
        raise NotImplementedError


@register_builtin('type.__subclasses__')
@check_result
def _do_type_subclasses(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    c = args[0]
    assert isinstance(c, EClass), c
    return Result(sorted(list(c.subclasses)))


@register_builtin('type.__call__')
@check_result
def _do_type_call(args: Tuple[Any, ...], kwargs: Dict[Text, Any],
                  globals_: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    return args[0].instantiate(args[1:], kwargs, globals_, ictx)


@register_builtin('type')
@check_result
def _do_type(args: Tuple[Any, ...], kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    assert not kwargs, kwargs
    assert isinstance(args, tuple), args
    log('go:type()', lambda: f'args: {args}')
    if len(args) == 1:
        if isinstance(args[0], EPyObject):
            return Result(args[0].get_type())
        res = type(args[0])
        return Result(TYPE_TO_EBUILTIN.get(res, res))

    assert len(args) == 3, args
    name, bases, ns = args

    cls = EClass(name, ns, bases=bases)

    if '__classcell__' in ns:
        ns['__classcell__'].set(cls)
        del ns['__classcell__']

    return Result(cls)

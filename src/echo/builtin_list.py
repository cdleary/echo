from typing import Text, Tuple, Any, Dict, Optional, List

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, check_result, ExceptionData
from echo import interp_routines
from echo import iteration_helpers
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, get_guest_builtin, is_list_builtin,
)
from echo.interp_context import ICtx


@register_builtin('list')
@check_result
def _do_list_call(args: Tuple[Any, ...],
                  kwargs: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
    log('list:call', f'args: {args} kwargs: {kwargs}')
    if isinstance(args[0], EPyObject):
        assert len(args) == 1 and not kwargs, (args, kwargs)
        items = []

        def cb(elem) -> Result[bool]:
            items.append(elem)
            return Result(True)

        res = iteration_helpers.foreach(args[0], cb, ictx)
        if res.is_exception():
            return res
        return Result(items)

    return Result(list(*args, **kwargs))


@register_builtin('list.__new__')
@check_result
def _do_list_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1 and not kwargs, (args, kwargs)
    storage = list(*args[1:])
    if isinstance(args[0], EClass):
        inst = EInstance(args[0])
        inst.builtin_storage[list] = storage
        return Result(inst)
    if is_list_builtin(args[0]):
        return Result(storage)
    raise NotImplementedError(args, kwargs)


@register_builtin('list.__init__')
def _do_list_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(None)


def _resolve(x: Any) -> List:
    if isinstance(x, EPyObject):
        return x.builtin_storage[list]
    if isinstance(x, list):
        return x
    # Raise type error.
    raise NotImplementedError(x)


@register_builtin('list.append')
def _do_list_append(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    _resolve(args[0]).append(args[1])
    return Result(None)


@register_builtin('list.extend')
def _do_list_extend(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    _resolve(args[0]).extend(args[1])
    return Result(None)


@register_builtin('list.clear')
def _do_list_append(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    _resolve(args[0]).clear()
    return Result(None)


@register_builtin('list.remove')
def _do_list_append(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    try:
        _resolve(args[0]).remove(args[1])
    except ValueError as e:
        return Result(ExceptionData(None, None, e))
    return Result(None)


@register_builtin('list.__eq__')
def _do_list_eq(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    lhs, rhs = map(_resolve, args)
    if len(lhs) != len(rhs):
        return Result(False)
    for a, b in zip(lhs, rhs):
        res = interp_routines.compare('==', a, b, ictx)
        if res.is_exception():
            return res
        equal = res.get_value()
        assert isinstance(equal, bool)
        if not equal:
            return Result(False)
    return Result(True)


@register_builtin('list.__contains__')
def _do_list_contains(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    lhs = _resolve(args[0])
    rhs = args[1]
    for e in lhs:
        res = interp_routines.compare('==', e, rhs, ictx)
        if res.is_exception():
            return res
        equal = res.get_value()
        assert isinstance(equal, bool)
        if equal:
            return Result(True)
    return Result(False)


@register_builtin('list.__iter__')
def _do_list_iter(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    lhs = _resolve(args[0])
    return Result(iter(lhs))


@register_builtin('list.__setitem__')
def _do_list_setitem(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 3 and not kwargs, (args, kwargs)
    lst, name, value = args
    lst = _resolve(lst)

    if isinstance(name, slice):
        do_list = get_guest_builtin('list')
        res = do_list.invoke((value,), {}, {}, ictx)
        if res.is_exception():
            return value
        value = res.get_value()

    lst[name] = value
    return Result(None)


@register_builtin('list.__getitem__')
def _do_list_setitem(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    # Note that list[int] will use the unbound list type and do getitem with a
    # type of int on the RHS -- this is supposed to give back a
    # "types.GenericAlias".
    assert len(args) == 2 and not kwargs, (args, kwargs)
    lst, index = args
    lst = _resolve(lst)

    if isinstance(index, int):
        return Result(lst[index])

    raise NotImplementedError(lst, index)

from typing import Tuple, Any, Dict, Text

from echo.eobjects import (
    register_builtin, EPyObject, EClass, EBuiltin, EPyType, EFunction,
    is_tuple_builtin, is_list_builtin, get_guest_builtin,
    GuestCoroutineType, EMethodType,
    # TODO fix privateness of this
    _is_type_builtin, _is_str_builtin, _is_int_builtin, _is_dict_builtin,
    _is_object_builtin, _is_bool_builtin,
)
from echo.elog import debugged, log
from echo.dso_objects import DsoPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo.interp_context import ICtx


@register_builtin('isinstance')
@check_result
def _do_isinstance(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args
    log('eo:isinstance', lambda: f'args: {args}')

    if (isinstance(args[1], EClass) and
            args[1].hasattr('__instancecheck__')):
        ic = args[1].getattr('__instancecheck__', ictx)
        if ic.is_exception():
            return Result(ic.get_exception())
        ic = ic.get_value()
        result = ictx.call(ic, (args[0],), {}, {},
                           globals_=getattr(ic, 'globals_', None))
        return result

    if isinstance(args[0], EFunction) and args[1] is EMethodType.singleton:
        return Result(False)

    for t in (bool, int, str, float, dict, list, tuple, set):
        if args[1] is t:
            return Result(isinstance(args[0], t))

    if (isinstance(args[0], str) and isinstance(args[1], tuple)
            and (get_guest_builtin('str') in args[1] or str in args[1])):
        return Result(True)

    if args[1] is type:
        return Result(isinstance(args[0], (type, EClass)))

    if isinstance(args[1], type) and issubclass(args[1], Exception):
        # TODO(leary) How does the real type builtin make it here?
        return Result(isinstance(args[0], args[1]))

    if (isinstance(args[0], BaseException) and
            args[1] is get_guest_builtin('BaseException')):
        return Result(True)

    if is_tuple_builtin(args[1]):
        if not isinstance(args[0], EPyObject):
            return Result(isinstance(args[0], tuple))
        raise NotImplementedError(args)

    if _is_type_builtin(args[1]):
        if _is_type_builtin(args[0]) or _is_object_builtin(args[0]):
            return Result(True)
        do_type = get_guest_builtin('type')
        lhs_type = do_type.invoke((args[0],), {}, {}, ictx)
        if lhs_type.is_exception():
            return Result(lhs_type.get_exception())
        result = _do_issubclass(
            (lhs_type.get_value(), get_guest_builtin('type')), {}, ictx)
        log('eo:isinstance', f'args: {args} result: {result}')
        return result

    if _is_str_builtin(args[1]):
        return Result(isinstance(args[0], str))

    if _is_dict_builtin(args[1]):
        return Result(isinstance(args[0], dict))

    if is_list_builtin(args[1]):
        return Result(isinstance(args[0], list))

    if _is_int_builtin(args[1]):
        return Result(isinstance(args[0], int))

    if _is_bool_builtin(args[1]):
        return Result(isinstance(args[0], bool))

    if _is_object_builtin(args[1]):
        return Result(True)  # Everything is an object.

    if args[0] is None:
        return Result(args[1] is type(None))  # noqa

    if (not isinstance(args[0], EPyObject)
            and isinstance(args[1], EClass)):
        return Result(type(args[0]) in args[1].get_mro())

    if (isinstance(args[0], EPyObject) and
            isinstance(args[1], EPyType)):
        return Result(args[1] in args[0].get_type().get_mro())

    if isinstance(args[0], EPyObject):
        if isinstance(args[1], (EClass, EBuiltin)):
            return Result(args[0].get_type() in args[1].get_mro())
        if args[0].get_type() == args[1]:
            return Result(True)

    if (not isinstance(args[0], EPyObject) and
            not isinstance(args[1], EPyObject) and
            not isinstance(args[1], tuple)):
        return Result(isinstance(args[0], args[1]))

    if isinstance(args[1], tuple):
        for item in args[1]:
            res = _do_isinstance((args[0], item), {}, ictx)
            if res.is_exception():
                return res
            ii = res.get_value()
            assert isinstance(ii, bool), ii
            if ii:
                return Result(True)
        return Result(False)

    raise NotImplementedError(args)


@debugged('eo:issubclass')
@register_builtin('issubclass')
@check_result
def _do_issubclass(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args

    if args[0] is args[1] and isinstance(args[0], EBuiltin):
        return Result(True)

    if (type(args[0]) is type and issubclass(args[0], BaseException) and
            args[1] is get_guest_builtin('BaseException')):
        return Result(True)

    if (isinstance(args[1], EPyObject) and
            not isinstance(args[1], DsoPyObject) and
            args[1].hasattr('__subclasscheck__')):
        scc = args[1].getattr('__subclasscheck__', ictx)
        if scc.is_exception():
            return Result(scc.get_exception())
        scc = scc.get_value()
        result = ictx.call(scc, (args[0],), {}, {},
                           globals_=getattr(scc, 'globals_', None))
        return result

    if isinstance(args[0], EClass) and isinstance(args[1], EBuiltin):
        log('eo:issubclass', 'args[0] EClass args[1] EBuiltin')
        return Result(args[0].is_subtype_of(args[1]))

    if isinstance(args[0], EPyType) and isinstance(args[1], EPyType):
        return Result(args[0].is_subtype_of(args[1]))

    if ((isinstance(args[0], EPyObject)
         and not isinstance(args[1], EPyObject)) or
        (not isinstance(args[0], EPyObject)
         and isinstance(args[1], EPyObject))):
        return Result(False)

    if isinstance(args[0], EBuiltin) and isinstance(args[1], EPyType):
        return Result(False)

    if isinstance(args[0], GuestCoroutineType):
        return Result(_is_type_builtin(args[1]))

    if _is_object_builtin(args[0]) and _is_type_builtin(args[1]):
        return Result(False)

    if _is_object_builtin(args[1]):
        return Result(True)

    if isinstance(args[1], GuestCoroutineType):
        return Result(False)

    if _is_type_builtin(args[1]):
        if isinstance(args[0], EPyObject):
            result = args[0].get_type().is_subtype_of(
                get_guest_builtin('type'))
            assert isinstance(result, bool), result
            return Result(result)
        if isinstance(args[0], type):
            return Result(issubclass(args[0], type))

    if isinstance(args[0], EPyType):
        return Result(args[1] in args[0].get_mro())

    if isinstance(args[0], type) and isinstance(args[1], type):
        return Result(issubclass(args[0], args[1]))

    raise NotImplementedError(args)


@register_builtin('repr')
@check_result
def _do_repr(args: Tuple[Any, ...], kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, EPyObject):
        return Result(repr(o))
    frepr = o.get_type().getattr('__repr__', ictx)
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    log('eo:do_repr()', f'o: {o} frepr: {frepr}')
    globals_ = getattr(frepr, 'globals_', None)
    return ictx.call(frepr, args=(o,), kwargs={}, locals_dict={},
                     globals_=globals_)

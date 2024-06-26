from typing import Text, Tuple, Any, Dict, Union, Type

from echo.epy_object import EPyType
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EClass, EBuiltin,
    get_guest_builtin,
)
from echo.interp_context import ICtx
from echo.elog import log


def _is_subtype_of(x, y):
    """Returns whether x is a subtype of y."""
    if isinstance(x, EPyType) and isinstance(y, EPyType):
        return x.is_subtype_of(y)
    if isinstance(x, type) and isinstance(y, type):
        return issubclass(x, y)
    raise NotImplementedError(x, y)


def _pytype_calculate_metaclass(
        metatype: EPyType,
        bases: Tuple[Union[EPyType, EBuiltin], ...],
        ictx: ICtx) -> Result[Union[EPyType, EBuiltin, Type]]:
    do_type = get_guest_builtin('type')

    winner: Union[EPyType, Type] = metatype
    for tmp in bases:
        tmptype = do_type.invoke((tmp,), {}, {}, ictx).get_value()
        assert isinstance(winner, (EPyType, EBuiltin, type)), winner
        assert isinstance(tmptype, (EPyType, EBuiltin, type)), tmptype
        if _is_subtype_of(winner, tmptype):
            continue
        if _is_subtype_of(tmptype, winner):
            winner = tmptype
            continue
        log('go:pcm', f'winner: {winner} tmptype: {tmptype}')
        msg = ('metaclass conflict: the metaclass of a derived class must be a'
               ' (non-strict subclass of the metaclasses of all its bases')
        return Result(ExceptionData(None, None, TypeError(msg)))
    return Result(winner)


@check_result
def _do___build_class__(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    log('go:build_class', f'args: {args}')
    func, name, *bases_lst = args
    assert isinstance(bases_lst, list), bases_lst
    bases: Tuple[Any, ...] = tuple(bases_lst)
    metaclass = kwargs.pop('metaclass', None) if kwargs else None
    if not metaclass:
        if bases:
            do_type = get_guest_builtin('type')
            metaclass = do_type.invoke((bases[0],), {}, {}, ictx)
            if metaclass.is_exception():
                return metaclass
            metaclass = metaclass.get_value()
            log('go:build_class', f'bases[0] start metaclass: {metaclass}')
            metaclass = _pytype_calculate_metaclass(metaclass, bases, ictx)
            if metaclass.is_exception():
                return metaclass
            metaclass = metaclass.get_value()
        else:
            metaclass = get_guest_builtin('type')

    if metaclass.hasattr('__prepare__'):
        prep_f = metaclass.getattr('__prepare__', ictx)
        if prep_f.is_exception():
            return Result(prep_f.get_exception())
        prep_f = prep_f.get_value()
        ns = ictx.call(prep_f,
                       (name, bases), kwargs, {}, globals_=prep_f.globals_)
        if ns.is_exception():
            return Result(ns.get_exception())
        ns = ns.get_value()
        log('bc:__build_class__',
            f'prepared ns via metaclass {metaclass} prep_f {prep_f}: {ns}')
    else:
        ns = {}  # Namespace for the class.

    # TODO(cdleary): 2019-12-15 At what point in the sequence do these get set?
    # res = do_setitem((ns, '__module__', func.globals_['__name__']), ictx)
    # if res.is_exception():
    #     return res

    class_eval_result = ictx.call(
        func, (), {}, locals_dict=ns, globals_=func.globals_)
    if class_eval_result.is_exception():
        return Result(class_eval_result.get_exception())
    cell = class_eval_result.get_value()
    if cell is None:
        if metaclass.hasattr('__new__'):
            new_f = metaclass.getattr('__new__', ictx).get_value()
            log('bc:__build_class__',
                f'invoking metaclass new: {new_f} ns: {ns}')
            return ictx.call(
                new_f, (metaclass, name, bases, ns), kwargs, {},
                globals_=new_f.globals_)
        return Result(EClass(name, ns, bases=bases, metaclass=metaclass))

    # TODO have to check for more derived metaclass or metaclass conflicts.

    # Now we call the metaclass with the evaluated namespace.
    assert isinstance(metaclass, (EClass, EBuiltin)), metaclass
    cls_result = ictx.call(metaclass, (name, bases, ns), {}, {})
    if cls_result.is_exception():
        return Result(cls_result.get_exception())

    # TODO(cdleary, 2019-02-16): Various checks that cell's class matches class
    # object.

    return cls_result


EBuiltin.register('__build_class__', _do___build_class__, None)

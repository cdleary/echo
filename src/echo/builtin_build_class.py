from typing import Text, Tuple, Any, Dict, Optional, Union

from echo.epy_object import EPyObject, EPyType
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EClass, EMethod, NativeFunction, EBuiltin,
    do_setitem, get_guest_builtin,
)
from echo.interp_context import ICtx
from echo.elog import log


def _pytype_calculate_metaclass(
        metatype: EPyType,
        bases: Tuple[EPyType, EBuiltin],
        ictx: ICtx) -> Result[Union[EPyType, EBuiltin]]:
    do_type = get_guest_builtin('type')

    winner = metatype
    for tmp in bases:
        tmptype = do_type.invoke((tmp,), {}, {}, ictx).get_value()
        assert isinstance(winner, (EPyType, EBuiltin)), winner
        assert isinstance(tmptype, (EPyType, EBuiltin)), tmptype
        if winner.is_subtype_of(tmptype):
            continue
        if tmptype.is_subtype_of(winner):
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
    func, name, *bases = args
    bases = tuple(bases)
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

    if metaclass != get_guest_builtin('type'):
        raise NotImplementedError(metaclass, cell)

    # Now we call the metaclass with the evaluated namespace.
    assert isinstance(metaclass, (EClass, EBuiltin)), metaclass
    cls_result = metaclass.invoke((name, bases, ns), {}, {}, ictx)
    if cls_result.is_exception():
        return Result(cls_result.get_exception())

    # TODO(cdleary, 2019-02-16): Various checks that cell's class matches class
    # object.

    return cls_result


EBuiltin.register('__build_class__', _do___build_class__, None)

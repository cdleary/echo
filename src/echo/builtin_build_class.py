from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo.guest_objects import (
    EFunction, EMethod, NativeFunction, EBuiltin, do_setitem, do_type,
)
from echo.interp_context import ICtx
from echo.guest_objects import EClass
from echo.elog import log


@check_result
def _do___build_class__(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[EClass]:
    log('go:build_class', f'args: {args}')
    func, name, *bases = args
    bases = tuple(bases)
    metaclass = kwargs.pop('metaclass', None) if kwargs else None
    if metaclass and metaclass.hasattr('__prepare__'):
        prep_f = metaclass.getattr('__prepare__', ictx)
        if prep_f.is_exception():
            return Result(prep_f.get_exception())
        prep_f = prep_f.get_value()
        ns = ictx.call(prep_f,
                       (name, bases), kwargs, {}, globals_=prep_f.globals_)
        if ns.is_exception():
            return Result(ns.get_exception())
        ns = ns.get_value()
        log('bc',
            f'prepared ns via metaclass {metaclass} prep_f {prep_f}: {ns}')
    else:
        ns = {}  # Namespace for the class.

    res = do_setitem((ns, '__module__', func.globals_['__name__']), ictx)
    if res.is_exception():
        return res

    class_eval_result = ictx.call(
        func, (), {}, locals_dict=ns, globals_=func.globals_)
    if class_eval_result.is_exception():
        return Result(class_eval_result.get_exception())
    cell = class_eval_result.get_value()
    if cell is None:
        if metaclass and metaclass.hasattr('__new__'):
            new_f = metaclass.getattr('__new__', ictx).get_value()
            log('bc', f'invoking metaclass new: {new_f} ns: {ns}')
            return ictx.call(
                new_f, (metaclass, name, bases, ns), kwargs, {},
                globals_=new_f.globals_)
        return Result(EClass(name, ns, bases=bases, metaclass=metaclass))

    if metaclass:
        raise NotImplementedError(metaclass, cell)

    # Now we call the metaclass with the evaluated namespace.
    cls_result = do_type((name, bases, ns), {})
    if cls_result.is_exception():
        return Result(cls_result.get_exception())

    # TODO(cdleary, 2019-02-16): Various checks that cell's class matches class
    # object.

    return cls_result


EBuiltin.register('__build_class__', _do___build_class__, None)

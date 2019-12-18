from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere
from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_exception_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


class EException(EPyObject):
    def __init__(self, args: Tuple[Any]):
        self.dict_ = {
            'args': args,
        }

    def get_type(self):
        return get_guest_builtin('Exception')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == 'args':
            return AttrWhere.SELF_DICT
        return None

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == 'args':
            return Result(self.dict_['args'])
        return Result(ExceptionData(None, None, AttributeError(name)))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


@register_builtin('Exception.__new__')
def _do_exception_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert 1 <= len(args) and not kwargs, (args, kwargs)
    msg = args[1] if len(args) == 2 else None
    if isinstance(args[0], EClass):
        inst = EInstance(args[0])
        return Result(inst)
    if _is_exception_builtin(args[0]):
        return Result(EException(tuple(args[1:])))
    raise NotImplementedError(args, kwargs)


@register_builtin('Exception.__init__')
def _do_exception_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(None)

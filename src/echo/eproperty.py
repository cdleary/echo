from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin,
)
from echo.elog import log
from echo.interp_context import ICtx


class EProperty(EPyObject):
    def __init__(self, fget: EFunction):
        self.fget = fget

    def get_type(self) -> EPyObject:
        return get_guest_builtin('property')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__get__', '__set__'):
            return AttrWhere.SELF_SPECIAL
        return None

    @check_result
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
        _self, obj, objtype = args
        if obj is None:
            return Result(self)
        log('ep:get', f'fget: {self.fget} obj: {obj} objtype: {objtype}')
        assert _self is self
        return self.fget.invoke((obj,), kwargs, locals_dict, ictx)

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'eproperty.__get__'), bound_self=self))
        return Result(ExceptionData(None, name, AttributeError(name)))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


@check_result
def _do_property(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]],
        ictx: ICtx) -> Result[Any]:
    if kwargs:
        raise NotImplementedError(kwargs)
    if len(args) != 1:
        raise NotImplementedError(args)
    guest_property = EProperty(args[0])
    return Result(guest_property)


EBuiltin.register('property', _do_property, EProperty)

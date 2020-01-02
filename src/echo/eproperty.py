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
    def __init__(self, fget: EPyObject, doc: Optional[Text]):
        assert isinstance(fget, EPyObject), fget
        self.fget = fget
        self.doc = doc

    def get_type(self) -> EPyObject:
        return get_guest_builtin('property')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__get__', '__set__', '__doc__'):
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
        do_call = self.fget.getattr('__call__', ictx)
        if do_call.is_exception():
            return do_call
        do_call = do_call.get_value()
        return do_call.invoke((obj,), kwargs, locals_dict, ictx)

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'eproperty.__get__'), bound_self=self))
        if name == '__doc__':
            return Result(self.doc)
        return Result(ExceptionData(None, name, AttributeError(name)))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


@check_result
def _do_property(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    doc = kwargs.pop('doc', None)
    assert len(args) == 1 and not kwargs, (args, kwargs)
    guest_property = EProperty(args[0], doc=doc)
    return Result(guest_property)


EBuiltin.register('property', _do_property, EProperty)

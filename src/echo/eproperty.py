from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere, EPyType, try_invoke
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin,
)
from echo.elog import log
from echo.interp_context import ICtx


class EProperty(EPyObject):
    def __init__(self, fget: EPyObject, fset: Optional[EPyObject],
                 doc: Optional[Text]):
        assert isinstance(fget, EPyObject), fget
        self.fget = fget
        self.fset = fset
        self.doc = doc

    def get_type(self) -> EPyType:
        return get_guest_builtin('property')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__get__', '__set__', '__doc__', 'fget', 'fset'):
            return AttrWhere.SELF_SPECIAL
        return None

    @check_result
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        _self, obj, objtype = args
        if obj is None:
            return Result(self)
        log('ep:get', f'fget: {self.fget} obj: {obj} objtype: {objtype}')
        assert _self is self
        do_call_ = self.fget.getattr('__call__', ictx)
        if do_call_.is_exception():
            return do_call_
        do_call = do_call_.get_value()
        return try_invoke(do_call, (obj,), kwargs, locals_dict, ictx)

    @check_result
    def _set(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        log('ep:set', f'fset: {self.fset} args: {args}')
        eself, obj, value = args
        assert eself is self
        if self.fset is None:
            raise NotImplementedError
        do_call_ = self.fset.getattr('__call__', ictx)
        if do_call_.is_exception():
            return do_call_
        do_call = do_call_.get_value()
        return try_invoke(do_call, (obj, value), kwargs, locals_dict, ictx)

    @check_result
    def _setter(self,
                args: Tuple[Any, ...],
                kwargs: Dict[Text, Any],
                locals_dict: Dict[Text, Any],
                ictx: ICtx,
                globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        _self, fset = args
        assert _self is self
        return Result(EProperty(self.fget, fset, self.doc))

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == 'fget':
            return Result(self.fget)
        if name == 'fset':
            return Result(self.fset)
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'eproperty.__get__'), bound_self=self))
        if name == '__set__':
            return Result(EMethod(NativeFunction(
                self._set, 'eproperty.__set__'), bound_self=self))
        if name == 'setter':
            return Result(EMethod(NativeFunction(
                self._setter, 'eproperty.setter'), bound_self=self))
        if name == '__doc__':
            return Result(self.doc)
        return Result(ExceptionData(None, name, AttributeError(name)))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        if name == '__doc__':
            self.doc = value
            return Result(None)
        raise NotImplementedError


@check_result
def _do_property(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    doc = kwargs.pop('doc', None)
    fget = kwargs.pop('fget', None)
    fset = kwargs.pop('fset', None)
    if len(args) == 0:
        pass
    elif len(args) == 1:
        assert fget is None
        fget = args[0]
    elif len(args) == 2:
        assert fget is None
        fget, fset = args
    else:
        raise NotImplementedError(args, kwargs)
    assert not kwargs, kwargs
    guest_property = EProperty(fget, fset, doc=doc)
    return Result(guest_property)


EBuiltin.register('property', _do_property, EProperty)

from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, check_result, ExceptionData
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, get_guest_builtin, invoke_desc,
    _is_type_builtin, _is_dict_builtin, _is_object_builtin,
    _is_int_builtin,
)
from echo.interp_context import ICtx


def _get_mro(o: EPyObject) -> Tuple[EPyObject, ...]:
    if isinstance(o, EBuiltin):
        return o.get_mro()
    assert isinstance(o, EClass), o
    return o.get_mro()


class ESuper(EPyObject):
    def __init__(self, type_, obj_or_type, obj_or_type_type):
        self.type_ = type_
        self.obj_or_type = obj_or_type
        self.obj_or_type_type = obj_or_type_type

    def has_standard_getattr(self) -> bool:
        return False

    @property
    def builtin_storage(self):
        return self.obj_or_type.builtin_storage

    def get_type(self) -> 'EPyObject':
        return get_guest_builtin('super')

    def __repr__(self) -> Text:
        return "<esuper: <class '{}'>, <{} object>>".format(
            self.type_.name, self.obj_or_type_type.name)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__thisclass__', '__self_class__', '__self__',
                    '__class__'):
            return AttrWhere.SELF_SPECIAL

        start_type = self.obj_or_type_type
        mro = _get_mro(start_type)
        # Look at everything succeeding 'type_' in the MRO order.
        i = mro.index(self.type_)
        mro = mro[i+1:]

        for t in mro:
            if isinstance(t, EBuiltin) and t.hasattr(name):
                return AttrWhere.CLS
            assert isinstance(t, EClass), t
            if name in t.dict_:
                return AttrWhere.SELF_SPECIAL

        return None

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__thisclass__':
            return Result(self.type_)
        if name == '__self_class__':
            return Result(self.obj_or_type_type)
        if name == '__self__':
            return Result(self.obj_or_type)
        if name == '__class__':
            return Result(get_guest_builtin('super'))

        start_type = self.obj_or_type_type
        mro = _get_mro(start_type)
        # Look at everything succeeding 'type_' in the MRO order.
        i = mro.index(self.type_)
        mro = mro[i+1:]

        for t in mro:
            if isinstance(t, EBuiltin):
                if t.hasattr(name):
                    cls_attr = t.getattr(name, ictx)
                else:
                    continue
            else:
                assert isinstance(t, EClass), (t, name)
                if name not in t.dict_:
                    continue
                # Name is in this class within the MRO, grab the attr.
                cls_attr = t.getattr(name, ictx)

            if cls_attr.is_exception():
                return cls_attr.get_exception()
            cls_attr = cls_attr.get_value()
            if (not isinstance(self.obj_or_type, EClass)
                    and cls_attr.hasattr('__get__')):
                return invoke_desc(self.obj_or_type, cls_attr, ictx)
            return Result(cls_attr)

        return Result(ExceptionData(
            None, None,
            AttributeError(f"'super' object has no attribute {name!r}")))

    def setattr(self, *args, **kwargs) -> Result[None]:
        return self.obj_or_type.setattr(*args, **kwargs)


@register_builtin('super')
@check_result
def _do_super(args: Tuple[Any, ...],
              kwargs: Dict[Text, Any],
              ictx: ICtx) -> Result[Any]:
    if not args:
        frame = ictx.interp_state.last_frame
        if frame is None:
            return Result(ExceptionData(
                traceback=None, parameter=None,
                exception=RuntimeError('super(): no current frame')))
        cell = next(cell for cell in frame.cellvars
                    if cell._name == '__class__')
        type_ = cell._storage
        if not isinstance(type_, EClass):
            raise NotImplementedError
        obj_or_type = frame.locals_[0]
    else:
        assert len(args) == 2, args
        type_, obj_or_type = args

    log('super', f'type_: {type_} obj: {obj_or_type}')

    def supercheck():
        if isinstance(obj_or_type, EClass):
            return obj_or_type
        assert isinstance(obj_or_type, EInstance)
        return obj_or_type.get_type()

    obj_type = supercheck()
    return Result(ESuper(type_, obj_or_type, obj_type))

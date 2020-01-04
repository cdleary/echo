from typing import Union, Text, Any, Optional, Tuple, Dict, Type
from echo.interp_context import ICtx
import types

from echo.elog import debugged
from echo import epy_object
from echo.epy_object import EPyObject, AttrWhere, EPyType
from echo.eobjects import EFunctionType
from echo.emodule import EModuleType
from echo.interp_result import Result, ExceptionData, check_result
from echo.ebuiltins import BUILTIN_VALUE_TYPES, BUILTIN_CONTAINER_TYPES


def _dso_lift_container(o: Any) -> Any:
    if type(o) == dict:
        return {_dso_lift(k): _dso_lift(v) for k, v in o.items()}
    if isinstance(o, tuple):
        return tuple(_dso_lift(e) for e in o)
    raise NotImplementedError(o, type(o))


@debugged('dso:lift')
def _dso_lift(o: Any) -> Any:
    if type(o) in BUILTIN_CONTAINER_TYPES:
        return _dso_lift_container(o)
    if type(o) in BUILTIN_VALUE_TYPES:
        return o
    if isinstance(o, (types.FunctionType, types.BuiltinFunctionType)):
        return DsoFunctionProxy(o)
    if type(o).__name__ == 'PyCapsule':
        return o
    if isinstance(o, type):
        if o in BUILTIN_VALUE_TYPES:
            return o
        else:
            return DsoClassProxy(o)
    return DsoInstanceProxy(o)


def _dso_unlift(o: Any) -> Any:
    if type(o) in BUILTIN_CONTAINER_TYPES:
        raise NotImplementedError(o)
    if type(o) in BUILTIN_VALUE_TYPES:
        return o
    raise NotImplementedError(o)


class DsoClassProxy(EPyType):
    def __init__(self, wrapped: Type):
        self.wrapped = wrapped

    def __repr__(self) -> Text:
        return f'<pclass {self.wrapped.__qualname__!r}>'

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return _dso_lift(self.wrapped.__mro__)

    def get_type(self) -> EPyObject:
        return DsoClassProxy(type(self.wrapped))

    @debugged('dso:c:ga')
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        try:
            o = getattr(self.wrapped, name)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        setattr(self.wrapped, name, _dso_unlift(value))
        return Result(None)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None


class DsoInstanceProxy(EPyObject):
    def __init__(self, wrapped: Any):
        self.wrapped = wrapped

    def get_type(self) -> EPyObject:
        return DsoClassProxy(type(self.wrapped))

    @debugged('dso:i:ga')
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        o = getattr(self.wrapped, name)
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        setattr(self.wrapped, name, _dso_unlift(value))
        return Result(None)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None


class DsoFunctionProxy(EPyObject):
    def __init__(self, wrapped: Union[types.FunctionType,
                                      types.BuiltinFunctionType]):
        self.wrapped = wrapped

    def __repr__(self) -> Text:
        return '<built-in pfunction {}>'.format(self.wrapped.__name__)

    def get_type(self) -> EPyObject:
        return EFunctionType.singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        try:
            o = getattr(self.wrapped, name)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        setattr(self.wrapped, name, _dso_unlift(value))
        return Result(None)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None

    @debugged('dso:f:invoke')
    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(ictx, ICtx), ictx
        with epy_object.establish_ictx(locals_dict, globals_, ictx):
            try:
                o = self.wrapped(*args, **kwargs)
            except BaseException as e:
                return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))


class DsoModuleProxy(EPyObject):
    def __init__(self, wrapped: types.ModuleType):
        assert isinstance(wrapped, types.ModuleType), wrapped
        self.wrapped = wrapped

    @property
    def filename(self) -> Text:
        return self.wrapped.__file__

    @property
    def fully_qualified_name(self) -> Text:
        return self.wrapped.__name__

    def get_type(self) -> EPyObject:
        return EModuleType.singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        o = getattr(self.wrapped, name)
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError(self, name, value)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None

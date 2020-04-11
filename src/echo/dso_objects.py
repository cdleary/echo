import functools
from typing import Union, Text, Any, Optional, Tuple, Dict, Type
from echo.interp_context import ICtx
import types

from echo import epy_object
from echo.elog import debugged
from echo.epy_object import EPyObject, AttrWhere, EPyType, safer_repr
from echo.eobjects import EFunctionType_singleton, EInstance, EFunction
from echo.emodule import EModuleType_singleton
from echo.interp_result import Result, ExceptionData, check_result
from echo.ebuiltins import (
    BUILTIN_VALUE_TYPES, BUILTIN_CONTAINER_TYPES, TYPE_TO_EBUILTIN,
)


def _dso_lift_container(o: Any) -> Any:
    if type(o) == dict:
        return {_dso_lift(k): _dso_lift(v) for k, v in o.items()}
    if type(o) is tuple:
        return tuple(_dso_lift(e) for e in o)
    if type(o) is list:
        return list(_dso_lift(e) for e in o)
    if type(o) is frozenset:
        return frozenset(_dso_lift(e) for e in o)
    raise NotImplementedError(o, type(o))


def _invoke_function(f: EFunction, *args, **kwargs):
    raise NotImplementedError(f, args, kwargs)


def _dso_unlift_container(o: Any, ictx: ICtx) -> Any:
    if type(o) is dict:
        return {_dso_unlift(k, ictx): _dso_unlift(v, ictx)
                for k, v in o.items()}
    if type(o) is tuple:
        return tuple(_dso_unlift(e, ictx) for e in o)
    if type(o) is list:
        return list(_dso_unlift(e, ictx) for e in o)
    raise NotImplementedError(o, type(o))


def _dso_lift(o: Any) -> Any:
    if type(o) in BUILTIN_CONTAINER_TYPES:
        return _dso_lift_container(o)
    if type(o) in BUILTIN_VALUE_TYPES:
        return o
    if isinstance(o, (types.FunctionType, types.BuiltinFunctionType,
                      types.MethodWrapperType)):
        return DsoFunctionProxy(o)
    if type(o).__name__ == 'PyCapsule':
        return o
    if isinstance(o, type):
        if o in TYPE_TO_EBUILTIN:
            return TYPE_TO_EBUILTIN[o]
        else:
            return DsoClassProxy(o)
    return DsoInstanceProxy(o)


def _dso_unlift(o: Any, ictx: ICtx) -> Any:
    if type(o) in BUILTIN_CONTAINER_TYPES:
        return _dso_unlift_container(o, ictx)
    if type(o) in BUILTIN_VALUE_TYPES:
        return o
    if type(o) in (DsoFunctionProxy, DsoInstanceProxy, DsoClassProxy):
        return o.wrapped
    if type(o) is EInstance and o.get_type().name == 'partial':
        return o
    if type(o) is EFunction:
        return functools.partial(_invoke_function, o)
    raise NotImplementedError(o)


class DsoPyObject(EPyObject):
    pass


class DsoClassProxy(EPyType, DsoPyObject):
    def __init__(self, wrapped: Type):
        assert wrapped is not type
        assert wrapped is not object
        self.wrapped = wrapped

    def __repr__(self) -> Text:
        return f'<pclass {self.wrapped.__qualname__!r}>'

    def get_name(self):
        return self.wrapped.__name__

    def get_dict(self) -> Dict[Text, Any]:
        return _dso_lift(dict(self.wrapped.__dict__))

    def get_bases(self) -> Tuple[EPyType, ...]:
        v = _dso_lift(self.wrapped.__bases__)
        assert isinstance(v, tuple), v
        return v

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return _dso_lift(self.wrapped.__mro__)

    def get_type(self) -> EPyType:
        return _dso_lift(type(self.wrapped))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        try:
            o = getattr(self.wrapped, name)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        setattr(self.wrapped, name, _dso_unlift(value, ictx))
        return Result(None)

    @debugged('dso:class:hasattr_where()')
    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            # Hack, we can't tell whether this is type's instancecheck because
            # it comes back as a built-in method.
            if name == '__instancecheck__':
                return None
            return AttrWhere.SELF_SPECIAL
        return None


class DsoInstanceProxy(DsoPyObject):
    def __init__(self, wrapped: Any):
        self.wrapped = wrapped

    def safer_repr(self) -> Text:
        return f'<pinstance {type(self.wrapped)!r}: {id(self.wrapped)}>'

    def __repr__(self) -> Text:
        return (f'<pinstance {type(self.wrapped)!r}: '
                f'{safer_repr(self.wrapped)}>')

    def get_type(self) -> EPyType:
        return _dso_lift(type(self.wrapped))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        try:
            o = getattr(self.wrapped, name)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        setattr(self.wrapped, name, _dso_unlift(value, ictx))
        return Result(None)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None


class DsoFunctionProxy(DsoPyObject):
    def __init__(self, wrapped: Union[types.FunctionType,
                                      types.BuiltinFunctionType]):
        self.wrapped = wrapped

    def __repr__(self) -> Text:
        return '<built-in pfunction {}>'.format(self.wrapped.__name__)

    def get_type(self) -> EPyType:
        return EFunctionType_singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        try:
            o = getattr(self.wrapped, name)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        setattr(self.wrapped, name, _dso_unlift(value, ictx))
        return Result(None)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(ictx, ICtx), ictx
        ulargs = _dso_unlift(args, ictx)
        ulkwargs = _dso_unlift(kwargs, ictx)
        with epy_object.establish_ictx(locals_dict, globals_, ictx):
            try:
                o = self.wrapped(*ulargs, **ulkwargs)
            except BaseException as e:
                return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))


class DsoModuleProxy(DsoPyObject):
    def __init__(self, wrapped: types.ModuleType):
        assert isinstance(wrapped, types.ModuleType), wrapped
        self.wrapped = wrapped

    @property
    def filename(self) -> Text:
        return self.wrapped.__file__

    @property
    def fully_qualified_name(self) -> Text:
        return self.wrapped.__name__

    def get_type(self) -> EPyType:
        return EModuleType_singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        try:
            o = getattr(self.wrapped, name)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        return Result(_dso_lift(o))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError(self, name, value)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if hasattr(self.wrapped, name):
            return AttrWhere.SELF_SPECIAL
        return None

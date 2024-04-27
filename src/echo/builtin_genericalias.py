# See for reference:
# https://github.com/python/cpython/blob/3.9/Objects/genericaliasobject.c

from typing import Text, Tuple, Any, Dict, Optional

from echo.enative_fn import ENativeFn
from echo.elog import log
from echo.epy_object import EPyObject, EPyType, AttrWhere
from echo.interp_result import Result, ExceptionData, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin, E_PREFIX
)
from echo.interp_context import ICtx
from echo import iteration_helpers


class EGenericAliasType(EPyType):

    def get_bases(self):
        raise NotImplementedError

    def get_dict(self):
        raise NotImplementedError

    def get_mro(self) -> Tuple[EPyType, ...]:
        raise NotImplementedError

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__call__':
            return Result(self)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == '__call__':
            return AttrWhere.SELF_SPECIAL
        if name == '__eq__':
            return AttrWhere.CLS
        raise NotImplementedError(name)

    def get_name(self) -> str:
        return 'types.GenericAlias'

    def __repr__(self) -> str:
        return f"<{E_PREFIX}class 'types.GenericAlias'>"

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None
               ) -> Result['EGenericAlias']:
        assert isinstance(ictx, ICtx), ictx
        origin, tup = args
        return Result(EGenericAlias(origin, tup))


EGenericAliasType_singleton = EGenericAliasType()


class EGenericAlias(EPyObject):
    def __init__(self, origin, args):
        self.origin = origin
        self.args = args

    def get_type(self) -> EPyType:
        return EGenericAliasType_singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__eq__':
            return Result(EMethod(ENativeFn(_do_ga_eq,
                                            'types.GenericAlias.__eq__'),
                                  bound_self=self))
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        raise NotImplementedError


@check_result
def _do_ga_eq(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        locals_dict: Dict[Text, Any],
        ictx: ICtx,
        globals_: Optional[Dict[Text, Any]] = None,
        ) -> Result[bool]:
    assert len(args) == 2 and not kwargs, (args, kwargs)
    lhs, rhs = args
    return Result(lhs.origin == rhs.origin and lhs.args == rhs.args)

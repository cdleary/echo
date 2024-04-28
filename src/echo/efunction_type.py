from typing import Tuple, Optional, Dict, Any

from echo.epy_object import EPyObject, EPyType, AttrWhere
from echo.interp_context import ICtx
from echo.interp_result import Result
from echo.eobjects import E_PREFIX, get_guest_builtin, EMethod
from echo.enative_fn import ENativeFn


class EFunctionType(EPyType):
    _singleton: Optional[EPyType] = None

    @classmethod
    def get_singleton(cls) -> EPyType:
        if cls._singleton is not None:
            return cls._singleton
        cls._singleton = EFunctionType()
        return cls._singleton

    def __repr__(self) -> str:
        return "<{}class 'function'>".format(E_PREFIX)

    def get_name(self) -> str: return 'function'

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def get_bases(self):
        raise NotImplementedError

    def get_dict(self):
        # TODO: return mapping proxy
        return {}

    def get_mro(self) -> Tuple[EPyType, ...]:
        return (self,)

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        if name in ('__code__', '__globals__', '__get__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def _get_desc(self, args, kwargs: Dict[str, Any],
                  locals_dict: Dict[str, Any],
                  ictx: ICtx,
                  globals_: Optional[Dict[str, Any]] = None) -> Result[Any]:
        assert not kwargs, kwargs
        assert len(args) == 3, args
        eself, obj, objtype = args
        if obj is None:
            return Result(eself)
        return Result(EMethod(eself, bound_self=obj))

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        if name in ('__code__', '__globals__'):
            return Result(None)

        if name == '__get__':
            return Result(ENativeFn(self._get_desc, 'efunction.__get__'))

        raise NotImplementedError

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

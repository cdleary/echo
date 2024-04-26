from typing import Any, Tuple, Optional

from echo.interp_context import ICtx
from echo.interp_result import Result

from echo.eobjects import get_guest_builtin
from echo.epy_object import (EPyObject, EPyType, AttrWhere)


class ECellType(EPyType):
    def get_name(self) -> str: return 'cell'

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def get_bases(self): raise NotImplementedError
    def get_dict(self): raise NotImplementedError
    def get_mro(self): raise NotImplementedError

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result((self, get_guest_builtin('type')))
        if name == '__name__':
            return Result(self.get_name())
        raise NotImplementedError(self, name)

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None


ECellType_singleton = ECellType()


class ECell(EPyObject):
    def __init__(self, name: str):
        self._name = name
        self._storage = ECell

    def get_type(self) -> EPyType:
        return ECellType_singleton

    def __repr__(self) -> str:
        return 'ECell(_name={!r}, _storage={})'.format(
            self._name,
            '<empty>' if self._storage is ECell else repr(self._storage))

    def initialized(self) -> bool:
        return self._storage is not ECell

    def get(self) -> Any:
        assert self._storage is not ECell, (
            'ECell %r is uninitialized' % self._name)
        return self._storage

    def set(self, value: Any) -> None:
        self._storage = value

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None

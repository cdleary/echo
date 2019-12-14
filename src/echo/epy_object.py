import abc
from enum import Enum
from typing import Text, Any, Optional, Tuple

from echo.interp_context import ICtx
from echo.interp_result import Result


class AttrWhere(Enum):
    SELF_DICT = 'self_dict'
    SELF_SPECIAL = 'self_special'
    CLS = 'cls'


class EPyObject(abc.ABC):

    @abc.abstractmethod
    def get_type(self) -> 'EPyObject':
        raise NotImplementedError

    @abc.abstractmethod
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

    @abc.abstractmethod
    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        raise NotImplementedError(self, name)

    def hasattr(self, name: Text) -> bool:
        return self.hasattr_where(name) is not None

    # @abc.abstractmethod
    def delattr(self, name: Text) -> Any:
        raise NotImplementedError(self, name)


class EPyType(EPyObject):

    def has_standard_getattr(self) -> bool:
        return True

    @abc.abstractmethod
    def get_mro(self) -> Tuple[EPyObject, ...]:
        raise NotImplementedError

    def is_subtype_of(self, other: EPyObject) -> bool:
        is_subtype = other in self.get_mro()
        if self is other:
            assert is_subtype
        return is_subtype

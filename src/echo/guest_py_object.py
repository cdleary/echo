import abc
from typing import Text, Any

from echo.interp_context import ICtx
from echo.interp_result import Result


class GuestPyObject(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

    def hasattr(self, name: Text) -> bool:
        raise NotImplementedError(self, name)

    # @abc.abstractmethod
    def delattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

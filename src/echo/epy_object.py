import abc
import contextlib
from enum import Enum
from typing import Text, Any, Optional, Tuple, Dict

from echo.interp_context import ICtx
from echo.interp_result import Result
from echo.elog import log


class AttrWhere(Enum):
    SELF_DICT = 'self_dict'
    SELF_SPECIAL = 'self_special'
    CLS = 'cls'


ictx_data = []


@contextlib.contextmanager
def establish_ictx(locals_dict: Dict[Text, Any],
                   globals_: Optional[Dict[Text, Any]],
                   ictx: ICtx):
    data = (locals_dict, globals_, ictx)
    ictx_data.append(data)
    yield
    popped = ictx_data.pop()
    assert popped is data


class NoContextException(Exception):
    pass


def _find_thread_ictx():
    if not ictx_data:
        raise NoContextException
    return ictx_data[-1]


class EPyObject(abc.ABC):

    def __call__(self, *args, **kwargs) -> Any:
        locals_dict, globals_, ictx = _find_thread_ictx()
        res = self.invoke(args, kwargs, locals_dict=locals_dict, ictx=ictx,
                          globals_=globals_)
        if res.is_exception():
            exc = res.get_exception().exception
            assert isinstance(exc, BaseException), exc
            raise exc
        return res.get_value()

    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        raise NotImplementedError(self)

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

    @abc.abstractmethod
    def get_bases(self) -> Tuple['EPyType', ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_dict(self) -> Dict[Text, Any]:
        raise NotImplementedError(self)

    def is_subtype_of(self, other: EPyObject) -> bool:
        mro = self.get_mro()
        log('epyo:iso', f'other: {other} mro: {mro}')
        is_subtype = other in mro
        if self is other:
            assert is_subtype
        return is_subtype

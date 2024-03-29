import abc
import contextlib
from enum import Enum
from typing import Text, Any, Optional, Tuple, Dict, Union, Type

from echo.interp_context import ICtx
from echo.interp_result import Result, ExceptionData
from echo.elog import log


def safer_repr(x: Any) -> Text:
    try:
        return repr(x)
    except NoContextException:
        if hasattr(x, 'safer_repr'):
            return x.safer_repr()
        return f'<reentrant {type(x)!r}: {id(x)}>'


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
    def get_type(self) -> 'EPyType':
        raise NotImplementedError

    @abc.abstractmethod
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
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
    """Abstract base class for type objects -- it is itself an EPyObject."""

    def has_standard_getattr(self) -> bool:
        return True

    @abc.abstractmethod
    def get_name(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def get_mro(self) -> Tuple[Union['EPyType', Type], ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_bases(self) -> Tuple['EPyType', ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_dict(self) -> Dict[Text, Any]:
        raise NotImplementedError(self)

    def is_subtype_of(self, other: 'EPyType') -> bool:
        mro = self.get_mro()
        log('epyo:iso', f'other: {other} mro: {mro}')
        is_subtype = other in mro
        if self is other:
            assert is_subtype
        return is_subtype


def try_invoke(o: EPyObject, args: Tuple[Any, ...], kwargs: Dict[str, Any],
               locals_dict: Dict[str, Any], ictx: ICtx) -> Result[Any]:
    if not hasattr(o, 'invoke'):
        return Result(ExceptionData(
            None, None, TypeError(
                'type {!r} is not callable'.format(o.get_type().get_name()))))
    return o.invoke(args, kwargs, locals_dict, ictx)

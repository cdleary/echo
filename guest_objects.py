import abc
import types
from typing import Text, Any, Dict, Iterable, Tuple

from interp_result import Result


class GuestPyObject:

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def getattr(self, name: Text) -> Any:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestModule(GuestPyObject):
    def __init__(self, name: Text, *, filename: Text, code: types.CodeType,
                 globals_: Dict[Text, Any]):
        self.name = name
        self.filename = filename
        self.code = code
        self.globals_ = globals_

    def __repr__(self):
        return 'GuestModule(name={!r}, filename={!r}, ...)'.format(
            self.name, self.filename)

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text) -> Any:
        return self.globals_[name]

    def setattr(self, name: Text, value: Any):
        assert not isinstance(value, Result), value
        self.globals_[name] = value


class GuestFunction(GuestPyObject):
    def __init__(self, code, globals_, name, *, defaults=None, closure=None):
        self.code = code
        self.globals_ = globals_
        self.name = name
        self.defaults = defaults
        self.closure = closure

    def __repr__(self):
        return ('_Function(code={!r}, name={!r}, closure={!r}, '
                'defaults={!r})').format(
                    self.code, self.name, self.closure, self.defaults)

    def invoke(self, args: Tuple[Any, ...], interp,
               state: 'InterpreterState') -> Result[Any]:
        return interp(self.code, globals_=self.globals_, args=args,
                      defaults=self.defaults, closure=self.closure,
                      in_function=True, state=state)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestInstance(GuestPyObject):

    def __init__(self, cls: 'GuestClass'):
        self.cls = cls
        self.dict = {}

    def getattr(self, name: Text) -> Any:
        return self.dict[name]

    def setattr(self, name: Text, value: Any):
        self.dict[name] = value


class GuestClass(GuestPyObject):
    def __init__(self, name, dict_, bases=None, metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or ()
        self.metaclass = metaclass
        self.kwargs = kwargs

    def __repr__(self) -> Text:
        return 'GuestClass(name={!r}, ...)'.format(self.name)

    def instantiate(self, args: Tuple[Any, ...], do_call,
                    globals_: Dict[Text, Any],
                    state: 'InterpreterState') -> Result[GuestInstance]:
        guest_instance = GuestInstance(self)
        if '__init__' in self.dict_:
            init_f = self.dict_['__init__']
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            result = do_call(init_f, args=(guest_instance,) + args,
                             state=state, globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestBuiltin(GuestPyObject):
    def __init__(self, name: Text, bound_self: Any):
        self.name = name
        self.bound_self = bound_self

    def __repr__(self):
        return 'GuestBuiltin(name={!r}, ...)'.format(self.name)

    def invoke(self, args: Tuple[Any, ...], interp,
               state: 'InterpreterState') -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        else:
            raise NotImplementedError(self.name)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestPartial(object):
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
        assert isinstance(f, GuestFunction), f
        self.f = f
        self.args = args

    def invoke(self, args: Tuple[Any, ...], interp,
               state: 'InterpreterState') -> Any:
        return self.f.invoke(self.args + args, interp=interp, state=state)

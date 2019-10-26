import abc
import itertools
import sys
import types
from typing import Text, Any, Dict, Iterable, Tuple, Optional, Set
from enum import Enum

from interp_result import Result, ExceptionData


class ReturnKind(Enum):
    RETURN = 'return'
    YIELD = 'yield'


class GuestPyObject(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

    # @abc.abstractmethod
    def delattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestModule(GuestPyObject):
    def __init__(self, fully_qualified_name: Text, *, filename: Text,
                 code: types.CodeType, globals_: Dict[Text, Any]):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.code = code
        self.globals_ = globals_

    def __repr__(self):
        return ('GuestModule(fully_qualified_name={!r}, '
                'filename={!r}, ...)'.format(
                    self.fully_qualified_name, self.filename))

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text) -> Result[Any]:
        if name == '__dict__':
            return Result(self.globals_)
        try:
            return Result(self.globals_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any):
        assert not isinstance(value, Result), value
        self.globals_[name] = value


class GuestFunction(GuestPyObject):
    def __init__(self, code, globals_, name, *, defaults=None,
                 kwarg_defaults: Optional[Dict[Text, Any]] = None,
                 closure=None):
        self.code = code
        self.globals_ = globals_
        self.name = name
        self.defaults = defaults
        self.kwarg_defaults = kwarg_defaults
        self.closure = closure
        self.dict_ = {}

    def __repr__(self):
        return ('GuestFunction(code={!r}, name={!r}, closure={!r}, '
                'defaults={!r}, kwarg_defaults={!r})').format(
                    self.code, self.name, self.closure, self.defaults,
                    self.kwarg_defaults)

    def invoke(self, *, args: Tuple[Any, ...],
               kwargs: Optional[Dict[Text, Any]], interp,
               locals_dict=None) -> Result[Any]:
        return interp(self.code, globals_=self.globals_, args=args,
                      kwargs=kwargs, defaults=self.defaults,
                      locals_dict=locals_dict,
                      kwarg_defaults=self.kwarg_defaults, closure=self.closure)

    def getattr(self, name: Text) -> Result[Any]:
        try:
            return Result(self.dict_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestGenerator(GuestPyObject):
    def __init__(self, f):
        self.f = f

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def next(self) -> Result[Any]:
        result = self.f.run_to_return_or_yield()
        if result.is_exception():
            return Result(result.get_exception())

        v, return_kind = result.get_value()
        if return_kind == ReturnKind.YIELD:
            return Result(v)

        assert v is None
        return Result(ExceptionData(None, None, StopIteration))


class GuestMethod(GuestPyObject):

    def __init__(self, f: GuestFunction, bound_self):
        self.f = f
        self.bound_self = bound_self

    def __repr__(self) -> Text:
        return 'GuestMethod(f={!r}, bound_self={!r})'.format(
            self.f, self.bound_self)

    @property
    def code(self): return self.f.code

    @property
    def globals_(self): return self.f.globals_

    @property
    def name(self): return self.f.name

    @property
    def defaults(self): return self.f.defaults

    @property
    def kwarg_defaults(self): return self.f.kwarg_defaults

    @property
    def closure(self): return self.f.closure

    def getattr(self, *args, **kwargs):
        return self.f.getattr(*args, **kwargs)

    def setattr(self, *args, **kwargs):
        return self.f.setattr(*args, **kwargs)

    def invoke(self, *, args: Tuple[Any, ...],
               kwargs: Optional[Dict[Text, Any]],
               locals_dict=None, interp) -> Result[Any]:
        return self.f.invoke(args=(self.bound_self,) + args, kwargs=kwargs,
                             locals_dict=locals_dict, interp=interp)


class GuestInstance(GuestPyObject):

    def __init__(self, cls: 'GuestClass'):
        self.cls = cls
        self.dict = {}

    def __repr__(self) -> Text:
        return 'GuestInstance(cls={!r})'.format(self.cls)

    def get_type(self) -> 'GuestClass':
        return self.cls

    def getattr(self, name: Text) -> Result[Any]:
        try:
            value = self.dict[name]
        except KeyError:
            result = self.cls.getattr(name)
            if result.is_exception():
                return result
            value = result.get_value()

        if isinstance(value, GuestFunction):
            return Result(GuestMethod(value, bound_self=self))
        return Result(value)

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
        return 'GuestClass(name={!r}, ...)'.format(
            self.name, self.dict_)

    def _get_transitive_bases(self) -> Set['GuestClass']:
        bases = set(self.bases)
        while True:
            new_bases = set(itertools.chain.from_iterable(
                c.bases for c in bases))
            size_before = len(bases)
            bases |= new_bases
            size_after = len(bases)
            if size_after == size_before:
                break
        return bases

    def is_subtype_of(self, other: 'GuestClass') -> bool:
        if self is other:
            return True
        return other in self._get_transitive_bases()

    def is_strict_subtype_of(self, other: 'GuestClass') -> bool:
        if self is other:
            return False
        return self.is_subtype_of(other)

    def instantiate(self, args: Tuple[Any, ...], do_call,
                    globals_: Dict[Text, Any]) -> Result[GuestInstance]:
        guest_instance = GuestInstance(self)
        if '__init__' in self.dict_:
            init_f = self.dict_['__init__']
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            result = do_call(init_f, args=(guest_instance,) + args,
                             globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    def getattr(self, name: Text) -> Result[Any]:
        return Result(self.dict_[name])

    def setattr(self, name: Text, value: Any) -> Any:
        self.dict_[name] = value


def _do_isinstance(args: Tuple[Any, ...]) -> Result[bool]:
    assert len(args) == 2, args
    if args[1] is int:
        return Result(isinstance(args[0], int))
    if args[1] is str:
        return Result(isinstance(args[0], str))
    if args[1] is type:
        return Result(isinstance(args[0], (type, GuestClass)))
    if issubclass(args[1], Exception):
        return Result(isinstance(args[0], args[1]))
    raise NotImplementedError(args)


def _do_issubclass(args: Tuple[Any, ...]) -> Result[bool]:
    # TODO(cdleary, 2019-02-10): Detect "guest" subclass relations.
    assert len(args) == 2, args
    return Result(issubclass(args[0], args[1]))


def _do_next(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 1, args
    g = args[0]
    assert isinstance(g, GuestGenerator), g
    return g.next()


def _do_type(args: Tuple[Any, ...]) -> Result[Any]:
    if len(args) == 1:
        if isinstance(args[0], GuestInstance):
            return Result(args[0].get_type())
        return Result(type(args[0]))
    assert len(args) == 3, args
    name, bases, ns = args

    cls = GuestClass(name, ns, bases=bases)

    if '__classcell__' in ns:
        ns['__classcell__'].set(cls)
        del ns['__classcell__']

    return Result(cls)


def _do___build_class__(args: Tuple[Any, ...], call) -> Result[GuestClass]:
    func, name, *bases = args
    ns = {}  # Namespace for the class.
    class_eval_result = call(func, args=(), locals_dict=ns,
                             globals_=func.globals_)
    if class_eval_result.is_exception():
        return class_eval_result.get_exception()
    cell = class_eval_result.get_value()
    if cell is None:
        return Result(GuestClass(name, ns))

    # Now we call the metaclass with the evaluated namespace.
    cls_result = _do_type(args=(name, bases, ns))
    if cls_result.is_exception():
        return Result(cls_result.get_exception())

    # TODO(cdleary, 2019-02-16): Various checks that cell's class matches class
    # object.

    return cls_result


class GuestSuper(GuestPyObject):
    def __init__(self, type_, obj):
        self.type_ = type_
        self.obj = obj

    def getattr(self, name: Text) -> Result[Any]:
        if name in self.obj.dict:
            result = Result(self.obj.dict[name])
        else:
            result = self.type_.getattr(name)
        if result.is_exception():
            return result
        value = result.get_value()
        if isinstance(value, GuestFunction):
            return Result(GuestMethod(value, bound_self=self))
        return Result(value)

    def setattr(self, name: Text, value: Any) -> Result[None]:
        return self.obj.setattr(name, value)


def _do_super(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 2
    type_, obj = args

    assert obj.get_type().is_subtype_of(type_)
    return Result(GuestSuper(type_.bases[0], obj))


_ITER_BUILTIN_TYPES = (
    tuple, str, bytes, bytearray, type({}.keys()), type({}.values()),
    type({}.items()), list, type(reversed([])), type(range(0, 0)),
    set, type(zip((), ())),
)


def _do_iter(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 1

    if isinstance(args[0], _ITER_BUILTIN_TYPES):
        return Result(iter(args[0]))
    raise NotImplementedError(args)


class GuestBuiltin(GuestPyObject):
    def __init__(self, name: Text, bound_self: Any):
        self.name = name
        self.bound_self = bound_self

    def __repr__(self):
        return 'GuestBuiltin(name={!r}, bound_self={!r}, ...)'.format(
            self.name, self.bound_self)

    def invoke(self, args: Tuple[Any, ...], interp, call) -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        if self.name == 'dict.values':
            assert not args, args
            return Result(self.bound_self.values())
        if self.name == 'dict.items':
            assert not args, args
            return Result(self.bound_self.items())
        if self.name == 'str.format':
            return Result(self.bound_self.format(*args))
        if self.name == 'list.append':
            return Result(self.bound_self.append(*args))
        if self.name == 'list.insert':
            return Result(self.bound_self.insert(*args))
        if self.name == 'list.remove':
            try:
                return Result(self.bound_self.remove(*args))
            except ValueError as e:
                return Result(ExceptionData(traceback=None, parameter=e.args,
                                            exception=ValueError))
        if self.name == 'zip':
            return Result(zip(*args))
        if self.name == 'reversed':
            return Result(reversed(*args))
        if self.name == 'set':
            return Result(set(*args))
        if self.name == 'isinstance':
            return _do_isinstance(args)
        if self.name == 'issubclass':
            return _do_issubclass(args)
        if self.name == '__build_class__':
            return _do___build_class__(args, call)
        if self.name == 'super':
            return _do_super(args)
        if self.name == 'iter':
            return _do_iter(args)
        if self.name == 'type':
            return _do_type(args)
        if self.name == 'next':
            return _do_next(args)
        raise NotImplementedError(self.name)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestPartial(object):
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
        assert isinstance(f, GuestFunction), f
        self.f = f
        self.args = args

    def invoke(self, args: Tuple[Any, ...], interp) -> Any:
        return self.f.invoke(args=self.args + args, kwargs=None, interp=interp)


class GuestCell:
    def __init__(self, name: Text):
        self._name = name
        self._storage = GuestCell

    def __repr__(self):
        return 'GuestCell(_name={!r}, _storage={})'.format(
            self._name,
            '<empty>' if self._storage is GuestCell else repr(self._storage))

    def initialized(self) -> bool:
        return self._storage is not GuestCell

    def get(self) -> Any:
        assert self._storage is not GuestCell, (
            'GuestCell %r is uninitialized' % self._name)
        return self._storage

    def set(self, value: Any):
        self._storage = value

import abc
import itertools
import os
import sys
import types
from typing import Text, Any, Dict, Iterable, Tuple, Optional, Set, Callable
from enum import Enum

from echo.interpreter_state import InterpreterState
from echo.code_attributes import CodeAttributes
from echo.interp_result import Result, ExceptionData
from echo.value import Value
from echo.common import memoize


DEBUG_PRINT_BYTECODE = bool(os.getenv('DEBUG_PRINT_BYTECODE', False))


class ReturnKind(Enum):
    RETURN = 'return'
    YIELD = 'yield'


class GuestPyObject(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

    def hasattr(self, name: Text) -> bool:
        raise NotImplementedError(self, name)

    # @abc.abstractmethod
    def delattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestModule(GuestPyObject):
    def __init__(self, fully_qualified_name: Text, *, filename: Text,
                 globals_: Dict[Text, Any]):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.globals_ = globals_

    def __repr__(self):
        return ('GuestModule(fully_qualified_name={!r}, '
                'filename={!r}, ...)'.format(
                    self.fully_qualified_name, self.filename))

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
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
    def __init__(self, code: types.CodeType, globals_, name, *, defaults=None,
                 kwarg_defaults: Optional[Dict[Text, Any]] = None,
                 closure=None):
        self.code = code
        self._code_attrs = CodeAttributes.from_code(code, name=name)
        self.globals_ = globals_
        self.name = name
        self.defaults = defaults
        self.kwarg_defaults = kwarg_defaults
        self.closure = closure
        self.dict_ = {
            '__code__': code,
        }

    def __repr__(self):
        return ('GuestFunction(code={!r}, name={!r}, closure={!r}, '
                'defaults={!r}, kwarg_defaults={!r})').format(
                    self.code, self.name, self.closure, self.defaults,
                    self.kwarg_defaults)

    def invoke(self, *, args: Tuple[Any, ...],
               interp_callback: Callable,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               locals_dict: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        if self._code_attrs.coroutine:
            return Result(GuestCoroutine(self))

        return interp_callback(
            self.code, globals_=self.globals_, args=args, kwargs=kwargs,
            defaults=self.defaults, locals_dict=locals_dict, name=self.name,
            kwarg_defaults=self.kwarg_defaults, closure=self.closure)

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        try:
            return Result(self.dict_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class GuestCoroutine(GuestPyObject):
    def __init__(self, f: GuestFunction):
        self.f = f

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == 'close':
            def fake(x): pass
            guest_f = GuestFunction(
                getattr(fake, '__code__'), {}, 'coroutine.close')
            guest_m = GuestMethod(guest_f, self)
            return Result(guest_m)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestAsyncGenerator(GuestPyObject):
    def __init__(self, f):
        self.f = f

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestTraceback(GuestPyObject):
    def __init__(self, data: Tuple[Text, ...]):
        self.data = data

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == 'tb_frame':
            return Result(None)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestGenerator(GuestPyObject):
    def __init__(self, f):
        self.f = f

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def next(self) -> Result[Value]:
        result = self.f.run_to_return_or_yield()
        if result.is_exception():
            return Result(result.get_exception())

        v, return_kind = result.get_value()
        assert isinstance(v, Value), v
        if return_kind == ReturnKind.YIELD:
            return Result(v.wrapped)

        assert v.wrapped is None, v
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
               interp_callback: Callable,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               locals_dict=None) -> Result[Any]:
        return self.f.invoke(
            args=(self.bound_self,) + args, kwargs=kwargs,
            interp_state=interp_state, locals_dict=locals_dict,
            interp_callback=interp_callback)


class GuestInstance(GuestPyObject):

    def __init__(self, cls: 'GuestClass'):
        assert isinstance(cls, GuestClass), cls
        self.cls = cls
        self.dict_ = {}

    def __repr__(self) -> Text:
        return '<{} object>'.format(self.cls.name)

    def get_type(self) -> 'GuestClass':
        return self.cls

    def hasattr(self, name: Text) -> bool:
        if name in self.dict_:
            return True
        if name == '__class__':
            return True
        cls_hasattr = self.cls.hasattr(name)
        assert isinstance(cls_hasattr, bool), (self.cls, cls_hasattr)
        return cls_hasattr

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        try:
            value = self.dict_[name]
        except KeyError:
            if name == '__class__':
                return Result(self.cls)
            if name == '__dict__':
                return Result(self.dict_)
            result = self.cls.getattr(name, interp_state=interp_state,
                                      interp_callback=interp_callback)
            if result.is_exception():
                return result
            value = result.get_value()
            if isinstance(value, GuestFunction):
                return Result(GuestMethod(value, bound_self=self))

        if (isinstance(value, (GuestInstance, GuestProperty)) and
                value.hasattr('__get__')):
            f_result = value.getattr('__get__', interp_state=interp_state,
                                     interp_callback=interp_callback)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            objtype_result = _do_type(args=(value,))
            if objtype_result.is_exception():
                return Result(objtype_result.get_exception())
            objtype = objtype_result.get_value()
            result = f_result.get_value().invoke(
                args=(value, objtype), interp_callback=interp_callback,
                interp_state=interp_state)
            if result.is_exception():
                return Result(result.get_exception())
            value = result.get_value()

        return Result(value)

    def setattr(self, name: Text, value: Any):
        self.dict_[name] = value


class GuestClass(GuestPyObject):
    def __init__(self, name: Text, dict_: Dict[Text, Any], *, bases=None,
                 metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or ()
        self.metaclass = metaclass
        self.kwargs = kwargs

    def __repr__(self) -> Text:
        return '<eclass \'{}.{}\'>'.format(self.dict_['__module__'], self.name)

    def get_type(self) -> 'GuestClass':
        return self.metaclass or get_guest_builtin('type')

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

    def instantiate(self, args: Tuple[Any, ...], *,
                    interp_state: InterpreterState,
                    do_call: Callable,
                    globals_: Dict[Text, Any]) -> Result[GuestInstance]:
        guest_instance = None
        if self.hasattr('__new__'):
            new_f = self.getattr(
                '__new__', interp_state=interp_state).get_value()
            result = do_call(new_f, args=(self,) + args, globals_=globals_)
            if result.is_exception():
                return Result(result.get_exception())
            guest_instance = result.get_value()
            if not _do_isinstance(args=(guest_instance, self)).get_value():
                return Result(guest_instance)
        guest_instance = guest_instance or GuestInstance(self)
        if self.hasattr('__init__'):
            init_f = self.getattr(
                '__init__', interp_state=interp_state).get_value()
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            result = do_call(init_f, args=(guest_instance,) + args,
                             globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    def hasattr(self, name: Text) -> bool:
        if name in self.dict_:
            return True
        if name == '__class__':
            return True
        if any(base.hasattr(name) for base in self.bases):
            return True
        if self.metaclass and self.metaclass.hasattr(name):
            return True
        return False

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == '__dict__':
            return Result(self.dict_)
        if name not in self.dict_:
            if name == '__class__':
                return Result(self.metaclass or get_guest_builtin('type'))
            if DEBUG_PRINT_BYTECODE:
                print('[go:ga] bases:', self.bases, 'metaclass:',
                      self.metaclass)
            for base in self.bases:
                if base.hasattr(name):
                    return base.getattr(name, interp_state=interp_state,
                                        interp_callback=interp_callback)
            if self.metaclass:
                if self.metaclass.hasattr(name):
                    return self.metaclass.getattr(
                        name, interp_state=interp_state,
                        interp_callback=interp_callback)
            return Result(ExceptionData(
                None,
                f'Class {self.name} does not have attribute {name!r}',
                AttributeError))
        return Result(self.dict_[name])

    def setattr(self, name: Text, value: Any) -> Any:
        self.dict_[name] = value


class GuestFunctionType(GuestPyObject):

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Callable,
                ) -> Result[Any]:
        if name in ('__code__', '__globals__'):
            return Result(None)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestCoroutineType(GuestPyObject):

    def hasattr(self, name: Text) -> bool:
        return False

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


def _is_type_builtin(x) -> bool:
    return isinstance(x, GuestBuiltin) and x.name == 'type'


def _is_str_builtin(x) -> bool:
    return isinstance(x, GuestBuiltin) and x.name == 'str'


def _do_isinstance(args: Tuple[Any, ...]) -> Result[bool]:
    assert len(args) == 2, args
    for t in (bool, int, str, float, dict, list, tuple, set):
        if args[1] is t:
            return Result(isinstance(args[0], t))
    if args[1] is type:
        return Result(isinstance(args[0], (type, GuestClass)))
    if isinstance(args[1], type) and issubclass(args[1], Exception):
        # TODO(leary) How does the real type builtin make it here?
        return Result(isinstance(args[0], args[1]))

    if _is_type_builtin(args[1]):
        type_types = (type, GuestClass, GuestFunctionType, GuestCoroutineType)
        return Result(isinstance(args[0], type_types))

    if _is_str_builtin(args[1]):
        return Result(isinstance(args[0], str))

    if args[0] is None:
        return Result(args[1] is type(None))  # noqa

    raise NotImplementedError(args)


def _do_issubclass(args: Tuple[Any, ...], call: Callable) -> Result[bool]:
    # TODO(cdleary, 2019-02-10): Detect "guest" subclass relations.
    assert len(args) == 2, args
    if DEBUG_PRINT_BYTECODE:
        print('[go:issubclass] arg0:', args[0], file=sys.stderr)
        print('[go:issubclass] arg1:', args[1], file=sys.stderr)

    if isinstance(args[0], GuestClass) and isinstance(args[1], GuestClass):
        return Result(args[0].is_subtype_of(args[1]))

    if isinstance(args[0], GuestCoroutineType):
        return Result(_is_type_builtin(args[1]))

    if (isinstance(args[1], GuestPyObject) and
            args[1].hasattr('__subclasscheck__')):
        scc = args[1].getattr('__subclasscheck__')
        if scc.is_exception():
            return Result(scc.get_exception())
        scc = scc.get_value()
        return call(scc, args=(args[1], args[0]), globals_=scc.globals_)

    if not isinstance(args[1], type):
        raise NotImplementedError(args)

    return Result(issubclass(args[0], args[1]))


def _do_next(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 1, args
    g = args[0]
    assert isinstance(g, GuestGenerator), g
    return g.next()


def _do_hasattr(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 2, args
    o, attr = args
    if not isinstance(o, GuestPyObject):
        return Result(hasattr(o, attr))
    assert isinstance(attr, str), attr
    b = o.hasattr(attr)
    assert isinstance(b, bool), b
    return Result(b)


def _do_repr(args: Tuple[Any, ...], do_call) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, GuestPyObject):
        return Result(repr(o))
    frepr = o.getattr('__repr__')
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    globals_ = frepr.getattr('__globals__')
    return do_call(frepr, args=(), globals_=globals_)


def _do_str(args: Tuple[Any, ...], do_call) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, GuestPyObject):
        return Result(repr(o))
    frepr = o.getattr('__str__')
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    globals_ = frepr.getattr('__globals__')
    return do_call(frepr, args=(), globals_=globals_)


def _do_dir(args: Tuple[Any, ...], do_call, *,
            interp_callback: Callable,
            interp_state: InterpreterState) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if isinstance(o, GuestPyObject):
        d = o.getattr('__dict__', interp_state=interp_state,
                      interp_callback=interp_callback)
        if d.is_exception():
            return d.get_exception()
        d = d.get_value()
        keys = set(d.keys())
        keys.add('__class__')
        keys.add('__dict__')
        if isinstance(o, GuestInstance):
            result = _do_dir(
                (o.cls,), do_call, interp_callback=interp_callback,
                interp_state=interp_state)
            if result.is_exception():
                return Result(result.get_exception())
            assert isinstance(result.get_value(), list), result
            keys |= set(result.get_value())
        return Result(sorted(list(keys)))
    return Result(dir(o))


def _do_type(args: Tuple[Any, ...]) -> Result[Any]:
    if len(args) == 1:
        if DEBUG_PRINT_BYTECODE:
            print('[go:type]', args, file=sys.stderr)
        if isinstance(args[0], GuestInstance):
            return Result(args[0].get_type())
        if isinstance(args[0], GuestClass):
            return Result(args[0].metaclass or get_guest_builtin('type'))
        if isinstance(args[0], GuestFunction):
            return Result(GuestFunctionType())
        if isinstance(args[0], GuestCoroutine):
            return Result(GuestCoroutineType())
        if _is_type_builtin(args[0]):
            return Result(args[0])
        res = type(args[0])
        return Result(get_guest_builtin('type') if res is type else res)
    assert len(args) == 3, args
    name, bases, ns = args

    cls = GuestClass(name, ns, bases=bases)

    if '__classcell__' in ns:
        ns['__classcell__'].set(cls)
        del ns['__classcell__']

    return Result(cls)


def _do___build_class__(
        args: Tuple[Any, ...],
        *,
        interp_state: InterpreterState,
        interp_callback: Callable,
        kwargs: Optional[Dict[Text, Any]] = None,
        call) -> Result[GuestClass]:
    if DEBUG_PRINT_BYTECODE:
        print('[go:bc]', args)
    func, name, *bases = args
    ns = {}  # Namespace for the class.
    class_eval_result = call(func, args=(), locals_dict=ns,
                             globals_=func.globals_)
    if class_eval_result.is_exception():
        return class_eval_result.get_exception()
    cell = class_eval_result.get_value()
    metaclass = kwargs.get('metaclass') if kwargs else None
    if cell is None:
        ns['__module__'] = func.globals_['__name__']
        if metaclass and metaclass.hasattr('__new__'):
            new_f = metaclass.getattr(
                '__new__', interp_state=interp_state,
                interp_callback=interp_callback).get_value()
            return call(new_f,
                        args=(metaclass, name, bases, ns), kwargs=kwargs,
                        globals_=new_f.globals_)
        return Result(GuestClass(name, ns, bases=bases, metaclass=metaclass))

    if metaclass:
        raise NotImplementedError(metaclass, cell)

    # Now we call the metaclass with the evaluated namespace.
    cls_result = _do_type(args=(name, bases, ns))
    if cls_result.is_exception():
        return Result(cls_result.get_exception())

    # TODO(cdleary, 2019-02-16): Various checks that cell's class matches class
    # object.

    return cls_result


class GuestSuper(GuestPyObject):
    def __init__(self, type_, obj, obj_type):
        self.type_ = type_
        self.obj = obj
        self.obj_type = obj_type

    def get_type(self) -> 'GuestPyObject':
        return get_guest_builtin('super')

    def __repr__(self) -> Text:
        return "<esuper: <class '{}'>, <{} object>>".format(
            self.type_.name, self.obj_type.name)

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name in self.obj.dict_:
            result = Result(self.obj.dict_[name])
        else:
            # TODO(cdleary): 2019-11-09 Replace with real MRO lookup.
            base = self.type_.bases[0]
            result = base.getattr(name, interp_state=interp_state)
        if result.is_exception():
            return result
        value = result.get_value()
        if isinstance(value, GuestFunction):
            return Result(GuestMethod(value, bound_self=self.obj))
        return Result(value)

    def setattr(self, name: Text, value: Any) -> Result[None]:
        return self.obj.setattr(name, value)


def _do_super(args: Tuple[Any, ...],
              interp_state: InterpreterState) -> Result[Any]:
    if not args:
        frame = interp_state.last_frame
        cell = next(cell for cell in frame.cellvars
                    if cell._name == '__class__')
        type_ = cell._storage
        if not isinstance(type_, GuestClass):
            raise NotImplementedError
        obj = frame.locals_[0]
    else:
        assert len(args) == 2, args
        type_, obj = args

    obj_type = obj.get_type()
    return Result(GuestSuper(type_, obj, obj_type))


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
    """A builtin function in the echo VM."""

    def __init__(self, name: Text, bound_self: Any, singleton_ok: bool = True):
        self.name = name
        self.bound_self = bound_self
        self.dict = {}

    def __repr__(self):
        return 'GuestBuiltin(name={!r}, bound_self={!r}, ...)'.format(
            self.name, self.bound_self)

    def is_subtype_of(self, other: 'GuestClass') -> bool:
        return False

    def invoke(self, args: Tuple[Any, ...], *,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               # Needed for interface compatibility.
               interp_callback: Callable,
               call: Callable) -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        if self.name == 'dict.values':
            assert not args, args
            return Result(self.bound_self.values())
        if self.name == 'dict.items':
            assert not args, args
            return Result(self.bound_self.items())
        if self.name == 'dict.update':
            return Result(self.bound_self.update(args[0]))
        if self.name == 'str.format':
            return Result(self.bound_self.format(*args))
        if self.name == 'str.join':
            return Result(self.bound_self.join(*args))
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
        if self.name == 'chr':
            return Result(chr(*args))
        if self.name == 'isinstance':
            return _do_isinstance(args)
        if self.name == 'issubclass':
            return _do_issubclass(args, call=call)
        if self.name == '__build_class__':
            return _do___build_class__(
                args, kwargs=kwargs, call=call, interp_state=interp_state,
                interp_callback=interp_callback)
        if self.name == 'super':
            return _do_super(args, interp_state)
        if self.name == 'iter':
            return _do_iter(args)
        if self.name == 'type':
            return _do_type(args)
        if self.name == 'next':
            return _do_next(args)
        if self.name == 'hasattr':
            return _do_hasattr(args)
        if self.name == 'repr':
            return _do_repr(args, call)
        if self.name == 'str':
            return _do_str(args, call)
        if self.name == 'dir':
            return _do_dir(args, call, interp_state=interp_state,
                           interp_callback=interp_callback)
        raise NotImplementedError(self.name)

    def hasattr(self, name: Text) -> bool:
        return name in self.dict

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Any:
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


@memoize
def get_guest_builtin(name: Text) -> GuestBuiltin:
    return GuestBuiltin(name, None)


class GuestPartial:
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
        assert isinstance(f, GuestFunction), f
        self.f = f
        self.args = args

    def invoke(self, args: Tuple[Any, ...], *,
               interp_state: InterpreterState,
               interp_callback: Callable) -> Any:
        return self.f.invoke(
            args=self.args + args, kwargs=None,
            interp_callback=interp_callback, interp_state=interp_state)


class NativeFunction(GuestPyObject):

    def __init__(self, f: Callable):
        self.f = f

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError

    def invoke(self, *, args: Tuple[Any, ...],
               interp_callback: Callable,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               locals_dict: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        return self.f(args, interp_state=interp_state,
                      interp_callback=interp_callback)


class GuestProperty(GuestPyObject):
    def __init__(self, fget: GuestFunction):
        self.fget = fget

    def hasattr(self, name: Text):
        return name in ('__get__', '__set__')

    def _get(self, args: Tuple[Any, ...], *,
             interp_state: InterpreterState,
             interp_callback: Callable) -> Result[Any]:
        obj, objtype = args
        return self.fget.invoke(args=(obj,), interp_callback=interp_callback,
                                interp_state=interp_state)

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None
                ) -> Result[Any]:
        if name == '__get__':
            return Result(NativeFunction(self._get))
        return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


class GuestClassMethod(GuestPyObject):
    def __init__(self, f: GuestFunction):
        self.f = f

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError(name)

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError(name, value)


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

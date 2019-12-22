import abc
import collections
import itertools
import os
import pprint
import sys
import types
from typing import (
    Text, Any, Dict, Iterable, Tuple, Optional, Set, Callable, Union,
)
import weakref

from echo.return_kind import ReturnKind
from echo.epy_object import EPyObject, AttrWhere, EPyType
from echo.elog import log, debugged
from echo.interpreter_state import InterpreterState
from echo.interp_context import ICtx
from echo.code_attributes import CodeAttributes
from echo.interp_result import Result, ExceptionData, check_result
from echo.value import Value
from echo.common import memoize


class EFunction(EPyObject):
    def __init__(self,
                 code: types.CodeType,
                 globals_: Dict[Text, Any],
                 name: Text,
                 *,
                 defaults=None,
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
            '__module__': None,
            '__doc__': None,
            '__qualname__': None,
            '__name__': name,
        }

    def get_type(self) -> EPyObject:
        return EFunctionType.singleton

    def __repr__(self):
        return '<efunction {} at {:#x}>'.format(self.name, id(self))

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
        if self._code_attrs.coroutine:
            return Result(GuestCoroutine(self))

        return ictx.interp_callback(
            self.code, globals_=self.globals_, args=args, kwargs=kwargs,
            defaults=self.defaults, locals_dict=locals_dict, name=self.name,
            kwarg_defaults=self.kwarg_defaults, closure=self.closure,
            ictx=ictx)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if name in ('__class__',):
            return AttrWhere.SELF_SPECIAL
        if name in ('__get__',):
            return AttrWhere.CLS
        return None

    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
        assert len(args) == 3, args
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(EMethod(f=_self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__class__':
            return Result(EFunctionType.singleton)
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'efunction.__get__'), bound_self=self))
        if name == '__call__':
            return Result(self)
        try:
            return Result(self.dict_[name])
        except KeyError:
            msg = f'Cannot find attribute {name} on {self}'
            return Result(ExceptionData(None, name, AttributeError(msg)))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class GuestCoroutine(EPyObject):
    def __init__(self, f: EFunction):
        self.f = f

    def get_type(self) -> EPyObject:
        return GuestCoroutineType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == 'close':
            return AttrWhere.CLS
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == 'close':
            def fake(x): pass
            guest_f = EFunction(
                getattr(fake, '__code__'), {}, 'coroutine.close')
            guest_m = EMethod(guest_f, self)
            return Result(guest_m)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class EAsyncGeneratorType(EPyObject):
    def __init__(self):
        self._dict = {}

    def __repr__(self) -> Text:
        return "<eclass 'async_generator'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result((self, get_guest_builtin('type')))
        if name == '__dict__':
            return Result(self._dict)
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None


EAsyncGeneratorType.singleton = EAsyncGeneratorType()


class EAsyncGenerator(EPyObject):
    def __init__(self, f):
        self.f = f

    def get_type(self) -> EPyObject:
        return EAsyncGeneratorType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class EMethodType(EPyObject):
    def __repr__(self) -> Text:
        return "<eclass 'method'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None


EMethodType.singleton = EMethodType()


class EMethod(EPyObject):

    def __init__(self, f: Union[EFunction, 'NativeFunction'], bound_self):
        self.f = f
        self.bound_self = bound_self

    def __repr__(self) -> Text:
        return '<ebound method {} of {!r}>'.format(
            self.f.name, self.bound_self)

    def get_type(self) -> EPyObject:
        return EMethodType.singleton

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

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__self__', '__func__'):
            return AttrWhere.SELF_SPECIAL
        if name == '__get__':
            return None
        return None

    def getattr(self, name: Text, *args, **kwargs) -> Result[Any]:
        if name == '__self__':
            return Result(self.bound_self)
        if name == '__func__':
            return Result(self.f)
        return self.f.getattr(name, *args, **kwargs)

    def setattr(self, *args, **kwargs):
        return self.f.setattr(*args, **kwargs)

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
        assert isinstance(args, tuple), args
        return self.f.invoke(
            (self.bound_self,) + args,
            kwargs, locals_dict, ictx)


class NotFoundSentinel:
    pass


NotFoundSentinel.singleton = NotFoundSentinel()


def _find_name_in_mro(type_: EPyType, name: Text, ictx: ICtx) -> Any:
    mro = type_.get_mro()
    log('eo:fnim', f'searching for {name} in {mro}')
    for cls in mro:
        if isinstance(cls, EBuiltin):
            if cls.hasattr(name):
                return cls.getattr(name, ictx).get_value()
        else:
            assert isinstance(cls, EClass), cls
            log('eo:fnim',
                f'searching for {name} in {cls.name} among {cls.dict_.keys()}')
            if name in cls.dict_:
                return cls.dict_[name]
    return NotFoundSentinel.singleton


def _type_getattro(type_: 'EClass', name: Text, ictx: ICtx) -> Result[Any]:
    if name == '__dict__':
        return Result(type_.dict_)
    if name == '__mro__':
        return Result(type_.get_mro())
    if name == '__class__':
        return Result(type_.metaclass or get_guest_builtin('type'))
    if name == '__bases__':
        return Result(type_.bases)

    metatype = type_.get_type()
    meta_attr = _find_name_in_mro(metatype, name, ictx)
    log('eo:ec:ga', f'type_: {type_} name: {name!r} metaclass: {metatype} '
                    f'meta_attr: {meta_attr}')
    if meta_attr is not NotFoundSentinel.singleton:
        if (isinstance(meta_attr, EPyObject)
                and meta_attr.hasattr('__get__')
                and meta_attr.hasattr('__set__')):
            log('gi:ga', f'overriding descriptor: {meta_attr}')
            f = meta_attr.getattr('__get__', ictx)
            if f.is_exception():
                return f
            f = f.get_value()
            return f.invoke((type_, metatype), {}, {}, ictx)

    attr = _find_name_in_mro(type_, name, ictx)
    if attr is not NotFoundSentinel.singleton:
        log('eo:ec:ga', f'dict attr {name!r} on {type_}: {attr}')
        if isinstance(attr, EPyObject) and attr.hasattr('__get__'):
            f_result = attr.getattr('__get__', ictx)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            f_result = f_result.get_value()
            res = f_result.invoke((None, type_), {}, {}, ictx)
            log('eo:ec:ga', f'invoked descriptor getter {f_result} => {res}')
            return res
        return Result(attr)

    if meta_attr is not NotFoundSentinel.singleton:
        if (isinstance(meta_attr, EPyObject)
                and meta_attr.hasattr('__get__')):
            log('gi:ga', f'non-overriding descriptor: {meta_attr}')
            f = meta_attr.getattr('__get__', ictx)
            if f.is_exception():
                return f
            f = f.get_value()
            return f.invoke((type_, metatype), {}, {}, ictx)
        return Result(meta_attr)

    if metatype.hasattr('__getattr__'):
        meta_ga = metatype.getattr('__getattr__', ictx)
        if meta_ga.is_exception():
            return meta_ga
        meta_ga = meta_ga.get_value()
        if meta_ga.hasattr('__get__'):
            meta_ga = invoke_desc(type_, meta_ga, ictx)
            if meta_ga.is_exception():
                return meta_ga
            meta_ga = meta_ga.get_value()
        return meta_ga.invoke((name,), {}, {}, ictx)

    msg = f'Class {type_.name} does not have attribute {name!r}'
    return Result(ExceptionData(
        None,
        None,
        AttributeError(msg)))


class EInstance(EPyObject):

    builtin_storage: Dict[type, Any]

    def __init__(self, cls: Union['EClass', 'EBuiltin']):
        assert isinstance(cls, (EClass, EBuiltin)), cls
        self.cls = cls
        self.dict_ = {}
        self.builtin_storage = {}

    def __repr__(self) -> Text:
        return '<{} eobject>'.format(self.cls.name)

    def __len__(self):
        raise NotImplementedError

    def get_type(self) -> Union['EClass', 'EBuiltin']:
        return self.cls

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        # Special members.
        if name in ('__class__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        cls_hasattr = self.cls.hasattr(name)
        assert isinstance(cls_hasattr, bool), (self.cls, cls_hasattr)
        return AttrWhere.CLS if cls_hasattr else None

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        """Looks up an attribute on this object instance."""
        cls_attr = _find_name_in_mro(self.get_type(), name, ictx)

        log('gi:ga', f'self: {self} name: {name} cls_attr: {cls_attr}')

        if (isinstance(cls_attr, EInstance)
                and cls_attr.hasattr('__get__')
                and cls_attr.hasattr('__set__')):
            log('gi:ga', f'overriding descriptor: {cls_attr}')
            # Overriding descriptor.
            return invoke_desc(self, cls_attr, ictx)

        try:
            return Result(self.dict_[name])
        except KeyError:
            if name == '__class__':
                return Result(self.cls)
            if name == '__dict__':
                return Result(self.dict_)

        log('eo:ei', f'cls_attr: {cls_attr}')
        if isinstance(cls_attr, EPyObject) and cls_attr.hasattr('__get__'):
            log('gi:ga', f'non-overriding descriptor: {cls_attr}')
            return invoke_desc(self, cls_attr, ictx)

        if cls_attr is not NotFoundSentinel.singleton:
            return Result(cls_attr)

        dunder_getattr = _find_name_in_mro(self.get_type(), '__getattr__',
                                           ictx)
        if dunder_getattr is not NotFoundSentinel.singleton:
            log('eo:ei:ga', f'__getattr__: {dunder_getattr}')
            if (isinstance(dunder_getattr, EPyObject)
                    and dunder_getattr.hasattr('__get__')):
                dunder_getattr = invoke_desc(self, dunder_getattr, ictx)
                if dunder_getattr.is_exception():
                    return dunder_getattr
                dunder_getattr = dunder_getattr.get_value()
            return dunder_getattr.invoke((name,), {}, {}, ictx)

        msg = f"'{self.cls.name}' object does not have attribute {name!r}"
        return Result(ExceptionData(None, None, AttributeError(msg)))

    @check_result
    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        cls_attr = None
        if name in self.cls.dict_:
            cls_attr = self.cls.dict_[name]

        if (isinstance(cls_attr, EInstance)
                and cls_attr.hasattr('__set__')):
            f_result = cls_attr.getattr('__set__', ictx)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            return f_result.get_value().invoke((self, value), {}, {}, ictx)

        self.dict_[name] = value
        return Result(None)


def register_builtin(
        name: Text,
        type_: Optional[type] = None) -> Callable[[Callable], Callable]:
    def fregister(f: Callable) -> Callable:
        EBuiltin.register(name, f, type_)
        return f
    return fregister


EClassOrBuiltin = Union['EClass', 'EBuiltin']


def _get_bases(c: EClassOrBuiltin) -> Tuple[EPyObject, ...]:
    assert isinstance(c, (EClass, EBuiltin)), c
    if isinstance(c, EClass):
        return c.bases
    if (_is_type_builtin(c) or _is_dict_builtin(c) or _is_int_builtin(c) or
            is_list_builtin(c)):
        return (get_guest_builtin('object'),)
    if _is_object_builtin(c):
        return ()
    if _is_exception_builtin(c):
        return (get_guest_builtin('BaseException'),)
    if _is_base_exception_builtin(c):
        return (get_guest_builtin('object'),)
    raise NotImplementedError(c)


class EClass(EPyType):
    """Represents a user-defined class."""

    bases: Tuple[EClassOrBuiltin, ...]
    metaclass: Optional[EClassOrBuiltin]
    subclasses: Set['EClass']

    def __init__(self, name: Text, dict_: Dict[Text, Any], *,
                 bases: Optional[Tuple[EClassOrBuiltin]] = None,
                 metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or (get_guest_builtin('object'),)
        self.metaclass = metaclass
        self.kwargs = kwargs
        self.subclasses = weakref.WeakSet()

        for base in self.bases:
            if isinstance(base, (EBuiltin, EClass)):
                base.note_subclass(self)

    def note_subclass(self, derived: 'EClass') -> None:
        self.subclasses.add(derived)

    def __repr__(self) -> Text:
        if isinstance(self.dict_, dict) and '__module__' in self.dict_:
            return '<eclass \'{}.{}\'>'.format(
                self.dict_['__module__'], self.name)
        return '<eclass \'{}\">'.format(self.name)

    def get_type(self) -> 'EClass':
        return self.metaclass or get_guest_builtin('type')

    def get_mro(self) -> Tuple['EPyObject', ...]:
        """The MRO is a preorder DFS of the 'derives from' relation."""
        derives_from = []  # (cls, base)
        frontier = collections.deque([self])
        while frontier:
            cls = frontier.popleft()
            bases = _get_bases(cls)
            for base in bases:
                derives_from.append((cls, base))
                frontier.append(base)

        cls_to_subclasses = collections.defaultdict(list)
        for cls, base in derives_from:
            cls_to_subclasses[base].append(cls)
        cls_to_subclasses = dict(cls_to_subclasses)

        ready = collections.deque([self])
        order = []

        def is_ready(c) -> bool:
            return all(sc in order for sc in cls_to_subclasses.get(c, []))

        assert is_ready(self)

        while ready:
            c = ready.popleft()
            order.append(c)
            for b in reversed(_get_bases(c)):
                if is_ready(b):
                    ready.appendleft(b)

        eobject = get_guest_builtin('object')

        if eobject not in order:
            order.append(eobject)
        return tuple(order)

    def instantiate(self,
                    args: Tuple[Any, ...],
                    kwargs: Dict[Text, Any],
                    globals_: Dict[Text, Any],
                    ictx: ICtx) -> Result[EInstance]:
        """Creates an instance of this user-defined class."""
        log('eo:gc', f'instantiate self: {self} args: {args} kwargs: {kwargs}')
        guest_instance = None
        if self.hasattr('__new__'):
            new_f = self.getattr('__new__', ictx).get_value()
            log('gc:new', f'new_f {new_f}')
            result = ictx.call(new_f, (self,) + args, kwargs, locals_dict={},
                               globals_=globals_)
            if result.is_exception():
                return Result(result.get_exception())
            guest_instance = result.get_value()
            if not _do_isinstance((guest_instance, self), ictx).get_value():
                return Result(guest_instance)
        guest_instance = (EInstance(self) if guest_instance is None
                          else guest_instance)
        if self.hasattr('__init__'):
            init_f = self.getattr('__init__', ictx).get_value()
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            assert isinstance(guest_instance, EPyObject), guest_instance
            result = ictx.call(init_f,
                               (guest_instance,) + args,
                               kwargs,
                               {},
                               globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    @debugged('eo:eclass:hasattr_where()')
    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if name in ('__class__', '__bases__', '__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        if self.get_type().hasattr(name):
            return AttrWhere.CLS
        for base in self.get_mro()[1:]:
            haw = base.hasattr_where(name)
            if haw:
                return haw
        return None

    @debugged('eo:ec:ga')
    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        """Looks up an attribute on this class object.

        This should effectively correspond to type_getattro.
        """
        return _type_getattro(self, name, ictx)

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        sa = _find_name_in_mro(self.get_type(), '__setattr__', ictx)
        if (sa is NotFoundSentinel.singleton
                or sa is get_guest_builtin('object.__setattr__')):
            self.dict_[name] = value
            log('eo:ec:setattr',
                f'updated self.dict_ {self.dict_} name {name} value {value}')
            return Result(None)
        log('eo:ec:setattr',
            f'self {self} name {name} value {value} => invoking {sa}')
        return sa.invoke((self, name, value), {}, {}, ictx)


class EFunctionType(EPyType):
    def __repr__(self) -> Text:
        return "<eclass 'function'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return (self,)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__code__', '__globals__', '__get__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def _get_desc(self, args, kwargs: Dict[Text, Any],
                  locals_dict: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
        assert not kwargs, kwargs
        assert len(args) == 3, args
        self, obj, objtype = args
        if obj is None:
            return Result(self)
        return Result(EMethod(self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name in ('__code__', '__globals__'):
            return Result(None)

        if name == '__get__':
            return Result(NativeFunction(self._get_desc, 'efunction.__get__'))

        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


EFunctionType.singleton = EFunctionType()


class GuestCoroutineType(EPyType):

    def __init__(self):
        self.dict_ = {}

    def __repr__(self) -> Text:
        return "<eclass 'coroutine'>"

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return (self, get_guest_builtin('type'))

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__dict__':
            return Result(self.dict_)
        raise NotImplementedError(name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(name, value)


GuestCoroutineType.singleton = GuestCoroutineType()


def _is_type_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'type'


def _is_dict_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'dict'


def _is_int_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'int'


def _is_bool_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'bool'


def is_list_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'list'


def _is_object_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'object'


def _is_exception_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'Exception'


def _is_base_exception_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'BaseException'


def _is_str_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'str'


def _is_tuple_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'tuple'


@check_result
def _do_len(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1
    if not isinstance(args[0], EPyObject):
        return Result(len(args[0]))
    do_len = args[0].getattr('__len__', ictx)
    if do_len.is_exception():
        return do_len
    do_len = do_len.get_value()
    res = do_len.invoke((), {}, {}, ictx)
    if res.is_exception():
        return res
    v = res.get_value()
    assert isinstance(v, int)  # For now.
    if v < 0:
        return Result(ExceptionData(
            None, None, ValueError('__len__() should return >= 0')))
    return Result(v)


@check_result
def _do_min(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[Any]:
    if (not isinstance(args[0], EPyObject) and
            not isinstance(args[1], EPyObject)):
        return Result(min(args[0], args[1]))
    do_lt = do_getattr((args[0], '__lt__',), {}, ictx)
    if do_lt.is_exception():
        return do_lt
    do_lt = do_lt.get_value()
    res = do_lt.invoke((args[1],), {}, {}, ictx)
    if res.is_exception():
        return res
    return Result(args[0] if res.get_value() else args[1])


@check_result
def _do_isinstance(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args
    log('eo:isinstance', f'args: {args}')

    if (isinstance(args[1], EClass) and
            args[1].hasattr('__instancecheck__')):
        ic = args[1].getattr('__instancecheck__', ictx)
        if ic.is_exception():
            return Result(ic.get_exception())
        ic = ic.get_value()
        result = ictx.call(ic, (args[0],), {}, {},
                           globals_=ic.globals_)
        return result

    for t in (bool, int, str, float, dict, list, tuple, set):
        if args[1] is t:
            return Result(isinstance(args[0], t))

    if (isinstance(args[0], str) and isinstance(args[1], tuple)
            and (get_guest_builtin('str') in args[1] or str in args[1])):
        return Result(True)

    if args[1] is type:
        return Result(isinstance(args[0], (type, EClass)))

    if isinstance(args[1], type) and issubclass(args[1], Exception):
        # TODO(leary) How does the real type builtin make it here?
        return Result(isinstance(args[0], args[1]))

    if _is_tuple_builtin(args[1]):
        if not isinstance(args[0], EPyObject):
            return Result(isinstance(args[0], tuple))
        raise NotImplementedError(args)

    if _is_type_builtin(args[1]):
        if _is_type_builtin(args[0]) or _is_object_builtin(args[0]):
            return Result(True)
        do_type = get_guest_builtin('type')
        lhs_type = do_type.invoke((args[0],), {}, {}, ictx)
        if lhs_type.is_exception():
            return Result(lhs_type.get_exception())
        result = _do_issubclass(
            (lhs_type.get_value(), get_guest_builtin('type')), ictx)
        log('eo:isinstance', f'args: {args} result: {result}')
        return result

    if _is_str_builtin(args[1]):
        return Result(isinstance(args[0], str))

    if _is_dict_builtin(args[1]):
        return Result(isinstance(args[0], dict))

    if is_list_builtin(args[1]):
        return Result(isinstance(args[0], list))

    if _is_int_builtin(args[1]):
        return Result(isinstance(args[0], int))

    if _is_bool_builtin(args[1]):
        return Result(isinstance(args[0], bool))

    if _is_object_builtin(args[1]):
        return Result(True)  # Everything is an object.

    if args[0] is None:
        return Result(args[1] is type(None))  # noqa

    if (not isinstance(args[0], EPyObject)
            and isinstance(args[1], EClass)):
        return Result(type(args[0]) in args[1].get_mro())

    if isinstance(args[0], EPyObject):
        if isinstance(args[1], EClass):
            return Result(args[0].get_type() in args[1].get_mro())
        if args[0].get_type() == args[1]:
            return Result(True)

    if (not isinstance(args[0], EPyObject) and
            not isinstance(args[1], EPyObject) and
            not isinstance(args[1], tuple)):
        return Result(isinstance(args[0], args[1]))

    if isinstance(args[1], tuple):
        for item in args[1]:
            res = _do_isinstance((args[0], item), ictx)
            if res.is_exception():
                return res
            ii = res.get_value()
            assert isinstance(ii, bool), ii
            if ii:
                return Result(True)
        return Result(False)

    raise NotImplementedError(args)


@check_result
def _do_issubclass(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args
    log('eo:issubclass', f'arg0: {args[0]}')
    log('eo:issubclass', f'arg1: {args[1]}')

    if args[0] is args[1] and isinstance(args[0], EBuiltin):
        return Result(True)

    if (isinstance(args[1], EPyObject) and
            args[1].hasattr('__subclasscheck__')):
        scc = args[1].getattr('__subclasscheck__', ictx)
        if scc.is_exception():
            return Result(scc.get_exception())
        scc = scc.get_value()
        result = ictx.call(scc, (args[0],), {}, {},
                           globals_=scc.globals_)
        return result

    if isinstance(args[0], EClass) and isinstance(args[1], EBuiltin):
        return Result(args[0].is_subtype_of(args[1]))

    if isinstance(args[0], EPyType) and isinstance(args[1], EPyType):
        return Result(args[0].is_subtype_of(args[1]))

    if ((isinstance(args[0], EPyObject)
         and not isinstance(args[1], EPyObject)) or
        (not isinstance(args[0], EPyObject)
         and isinstance(args[1], EPyObject))):
        return Result(False)

    if isinstance(args[0], EBuiltin) and isinstance(args[1], EPyType):
        return Result(False)

    if isinstance(args[0], GuestCoroutineType):
        return Result(_is_type_builtin(args[1]))

    if _is_object_builtin(args[0]) and _is_type_builtin(args[1]):
        return Result(False)

    if _is_object_builtin(args[1]):
        return Result(True)

    if isinstance(args[1], GuestCoroutineType):
        return Result(False)

    if _is_type_builtin(args[1]):
        if isinstance(args[0], EPyObject):
            result = args[0].get_type().is_subtype_of(
                get_guest_builtin('type'))
            assert isinstance(result, bool), result
            return Result(result)
        if isinstance(args[0], type):
            return Result(issubclass(args[0], type))

    if isinstance(args[0], EClass):
        return Result(args[1] in args[0].get_mro())

    if isinstance(args[0], type) and isinstance(args[1], type):
        return Result(issubclass(args[0], args[1]))

    raise NotImplementedError(args)


@check_result
def _do_repr(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, EPyObject):
        return Result(repr(o))
    frepr = o.getattr('__repr__', ictx)
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    log('eo:do_repr()', f'o: {o} frepr: {frepr}')
    globals_ = frepr.globals_
    return ictx.call(frepr, args=(), kwargs={}, locals_dict={},
                     globals_=globals_)


@check_result
def _do_object(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 0, args
    return Result(EInstance(cls=get_guest_builtin('object')))


@check_result
def _do_object_subclasshook(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(NotImplemented)


@check_result
def _do_object_eq(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert not kwargs
    assert len(args) == 2, args
    lhs, rhs = args
    return Result(NotImplemented)


@check_result
def _do_object_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    assert isinstance(args[0], (EClass, EBuiltin)), args
    return Result(EInstance(args[0]))


@check_result
def _do_object_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    assert isinstance(args[0], (EInstance)), args
    return Result(None)


@check_result
def _do_object_repr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    raise NotImplementedError(args[0])


@check_result
def _do_object_ne(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert not kwargs
    lhs, rhs = args
    return Result(NotImplemented)


@check_result
def _do_object_setattr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 3, args
    assert not kwargs
    o, name, value = args
    log('eo:object_setattr', f'o {o} name {name} value {value}')
    if isinstance(o, (EInstance, EClass)):
        o.dict_[name] = value
    else:
        raise NotImplementedError
    return Result(None)


@check_result
def _do_dir(args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if isinstance(o, EPyObject):
        d = o.getattr('__dict__', ictx)
        if d.is_exception():
            return d.get_exception()
        d = d.get_value()
        keys = set(d.keys())
        keys.add('__class__')
        keys.add('__dict__')
        if isinstance(o, EInstance):
            result = _do_dir((o.cls,), kwargs, ictx)
            if result.is_exception():
                return Result(result.get_exception())
            assert isinstance(result.get_value(), list), result
            keys |= set(result.get_value())
        return Result(sorted(list(keys)))
    return Result(dir(o))


_ITER_BUILTIN_TYPES = (
    tuple, str, bytes, bytearray, type({}.keys()), type({}.values()),
    type({}.items()), list, type(reversed([])), type(range(0, 0)),
    set, type(zip((), ())), frozenset, weakref.WeakSet, dict,
)


class EBuiltin(EPyType):
    """A builtin function/type in the echo VM."""

    BUILTIN_TYPES = (
        'object', 'type', 'dict', 'tuple', 'list', 'int', 'classmethod',
        'staticmethod', 'property', 'Exception', 'super', 'enumerate',
        'str',
    )
    BUILTIN_FNS = (
        'len', '__build_class__', 'getattr', 'iter', 'reversed', 'zip',
        'isinstance', 'issubclass', 'hasattr', 'any', 'min', 'callable',
        # object
        'object.__init__', 'object.__str__', 'object.__setattr__',
        'object.__format__', 'object.__reduce_ex__', 'object.__ne__',
        'object.__new__', 'object.__repr__',
        # type
        'type.__init__', 'type.__str__', 'type.__new__', 'type.__subclasses__',
        'type.mro', 'type.__call__',
        # str
        'str.maketrans', 'str.join',
        # dict
        'dict.__eq__', 'dict.__init__',
        'dict.__setitem__', 'dict.__getitem__', 'dict.__delitem__',
        'dict.__contains__',
        'dict.fromkeys', 'dict.update', 'dict.setdefault',
        'dict.pop', 'dict.get',
        # int
        'int.__new__', 'int.__add__', 'int.__init__', 'int.__sub__',
        'int.__repr__', 'int.__str__', 'int.__int__',
        'int.__and__', 'int.__rand__', 'int.__mul__',
        'int.__rmul__', 'int.__bool__',
        # int cmp
        'int.__eq__', 'int.__lt__', 'int.__ge__', 'int.__le__', 'int.__gt__',
        # list
        'list.__new__', 'list.__init__', 'list.__eq__', 'list.append',
        'list.extend', 'list.clear', 'list.__contains__', 'list.__iter__',
    )

    _registry: Dict[Text, Tuple[Callable, Optional[type]]] = {}

    def __init__(self, name: Text, bound_self: Any, singleton_ok: bool = True):
        self.name = name
        self.bound_self = bound_self
        self.dict = {}
        self.globals_ = {}

    def has_standard_getattr(self) -> bool:
        if self.name in ('super',):
            return False
        return True

    @classmethod
    def is_ebuiltin(cls, o: Any) -> bool:
        if isinstance(o, EBuiltin):
            return True
        return o in cls._registry.values()

    @classmethod
    def get_ebuiltin_type(cls, name: Text) -> type:
        t = cls._registry[name][1]
        assert t is not None
        return t

    @classmethod
    def register(cls, name: Text, f: Callable, t: Optional[type]) -> None:
        cls._registry[name] = (f, t)

    def __repr__(self):
        if self.name in self.BUILTIN_TYPES:
            return "<eclass '{}'>".format(self.name)
        if self.name in self.BUILTIN_FNS:
            return f'<ebuilt-in function {self.name}>'
        return 'EBuiltin(name={!r}, bound_self={!r}, ...)'.format(
            self.name, self.bound_self)

    def get_type(self) -> EPyObject:
        if self.name in self.BUILTIN_FNS:
            if self.bound_self:
                return EMethodType.singleton
            else:
                return EFunctionType.singleton
        if self.name in self.BUILTIN_TYPES:
            return get_guest_builtin('type')
        raise NotImplementedError(self)

    def get_mro(self) -> Tuple['EPyObject', ...]:
        if self.name == 'object':
            return (get_guest_builtin('object'),)
        elif self.name in self.BUILTIN_TYPES:
            return (get_guest_builtin(self.name), get_guest_builtin('object'))
        else:
            raise NotImplementedError(self)

    def note_subclass(self, cls: 'EClass') -> None:
        pass

    def is_subtype_of(self, other: EPyType) -> bool:
        if _is_type_builtin(self) and _is_object_builtin(other):
            return True
        if self is other:
            return True
        return False

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
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
        if self.name == 'zip':
            return Result(zip(*args))
        if self.name == 'reversed':
            return Result(reversed(*args))
        if self.name == 'chr':
            return Result(chr(*args))
        if self.name == 'len':
            return _do_len(args, ictx)
        if self.name == 'min':
            return _do_min(args, ictx)
        if self.name == 'isinstance':
            return _do_isinstance(args, ictx)
        if self.name == 'issubclass':
            return _do_issubclass(args, ictx)
        if self.name == 'object.__subclasshook__':
            return _do_object_subclasshook(args, kwargs, ictx)
        if self.name == 'object.__new__':
            return _do_object_new(args, kwargs, ictx)
        if self.name == 'object.__init__':
            return _do_object_init(args, kwargs, ictx)
        if self.name == 'object.__repr__':
            if self.bound_self is not None:
                args = (self.bound_self,) + args
            return _do_object_repr(args, kwargs, ictx)
        if self.name == 'object.__eq__':
            return _do_object_eq(args, kwargs, ictx)
        if self.name == 'object.__ne__':
            return _do_object_ne(args, kwargs, ictx)
        if self.name == 'object.__setattr__':
            return _do_object_setattr(args, kwargs, ictx)
        if self.name == 'iter':
            return do_iter(args, ictx)
        if self.name == 'next':
            return do_next(args, ictx)
        if self.name == 'hasattr':
            return do_hasattr(args, ictx)
        if self.name == 'repr':
            return _do_repr(args, ictx)
        if self.name == 'object':
            return _do_object(args)
        if self.name == 'dir':
            return _do_dir(args, kwargs, ictx)
        if self.name == 'getattr':
            return do_getattr(args, kwargs, ictx)
        if self.name in self._registry:
            if self.bound_self is not None:
                args = (self.bound_self,) + args
            return self._registry[self.name][0](args, kwargs, ictx)
        raise NotImplementedError(self.name)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict:
            return AttrWhere.SELF_DICT
        if self.name == 'dict' and name in (
                'update', 'setdefault', 'pop', 'get', '__eq__', '__getitem__',
                '__setitem__', '__delitem__', '__contains__'):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'list' and name in (
                'append', 'extend', 'clear', '__eq__', '__getitem__',
                '__setitem__', '__delitem__', '__contains__', '__iter__'):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'int' and name in (
                '__add__', '__init__', '__repr__', '__sub__', '__lt__',
                '__int__', '__eq__', '__and__', '__rand__', '__mul__',
                '__rmul__', '__bool__', '__ge__', '__le__', '__gt__'):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'str' and name in ('maketrans',):
            return AttrWhere.SELF_SPECIAL
        if (self.name in self.BUILTIN_TYPES
                and name in ('__mro__', '__dict__',)):
            return AttrWhere.SELF_SPECIAL
        if self.name in self.BUILTIN_FNS and name == '__get__':
            return AttrWhere.CLS
        if (self.name in self.BUILTIN_TYPES
                and name in ('__new__', '__init__', '__dict__', '__str__',
                             '__repr__', '__eq__', '__ne__', '__new__',
                             '__name__')):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'object' and name in (
                '__subclasshook__', '__bases__', '__setattr__'):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'type' and name in ('__subclasses__', 'mro',
                                            '__call__'):
            return AttrWhere.SELF_SPECIAL
        if name == '__eq__':
            return AttrWhere.CLS
        return None

    @debugged('eo:ebi')
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
        assert len(args) == 3, args
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(EMethod(f=_self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__self__' and self.bound_self is not None:
            return Result(self.bound_self)

        if self.name == 'str':
            if name == 'maketrans':
                return Result(get_guest_builtin('str.maketrans'))
            if name == 'join':
                return Result(get_guest_builtin('str.join'))

        if self.name == 'int':
            if name == '__new__':
                return Result(get_guest_builtin('int.__new__'))
            if name == '__add__':
                return Result(get_guest_builtin('int.__add__'))
            if name == '__init__':
                return Result(get_guest_builtin('int.__init__'))
            if name == '__repr__':
                return Result(get_guest_builtin('int.__repr__'))
            if name == '__str__':
                return Result(get_guest_builtin('int.__str__'))
            if name == '__sub__':
                return Result(get_guest_builtin('int.__sub__'))
            if name == '__lt__':
                return Result(get_guest_builtin('int.__lt__'))
            if name == '__int__':
                return Result(get_guest_builtin('int.__int__'))
            if name == '__and__':
                return Result(get_guest_builtin('int.__and__'))
            if name == '__bool__':
                return Result(get_guest_builtin('int.__bool__'))
            if name == '__mul__':
                return Result(get_guest_builtin('int.__mul__'))
            if name == '__rmul__':
                return Result(get_guest_builtin('int.__rmul__'))
            if name == '__rand__':
                return Result(get_guest_builtin('int.__rand__'))
            if name == '__eq__':
                return Result(get_guest_builtin('int.__eq__'))
            if name == '__ge__':
                return Result(get_guest_builtin('int.__ge__'))
            if name == '__le__':
                return Result(get_guest_builtin('int.__le__'))
            if name == '__gt__':
                return Result(get_guest_builtin('int.__gt__'))
            if name == '__dict__':
                return Result({
                    '__new__': get_guest_builtin('int.__new__'),
                    '__repr__': get_guest_builtin('int.__repr__'),
                })

        if self.name == 'Exception':
            if name == '__new__':
                return Result(get_guest_builtin('Exception.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('Exception.__init__'))

        if self.name == 'list':
            if name == '__new__':
                return Result(get_guest_builtin('list.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('list.__init__'))
            if name == '__eq__':
                return Result(get_guest_builtin('list.__eq__'))
            if name == '__contains__':
                return Result(get_guest_builtin('list.__contains__'))
            if name == '__iter__':
                return Result(get_guest_builtin('list.__iter__'))
            if name == 'append':
                return Result(get_guest_builtin('list.append'))
            if name == 'clear':
                return Result(get_guest_builtin('list.clear'))
            if name == 'extend':
                return Result(get_guest_builtin('list.extend'))

        if self.name == 'dict':
            if name == '__new__':
                return Result(get_guest_builtin('dict.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('dict.__init__'))
            if name == '__eq__':
                return Result(get_guest_builtin('dict.__eq__'))
            if name == '__getitem__':
                return Result(get_guest_builtin('dict.__getitem__'))
            if name == '__setitem__':
                return Result(get_guest_builtin('dict.__setitem__'))
            if name == '__contains__':
                return Result(get_guest_builtin('dict.__contains__'))
            if name == '__delitem__':
                return Result(get_guest_builtin('dict.__delitem__'))
            if name == 'update':
                return Result(get_guest_builtin('dict.update'))
            if name == '__dict__':
                return Result({
                    'fromkeys': get_guest_builtin('dict.fromkeys'),
                })
            if name == 'setdefault':
                return Result(get_guest_builtin('dict.setdefault'))
            if name == 'pop':
                return Result(get_guest_builtin('dict.pop'))
            if name == 'get':
                return Result(get_guest_builtin('dict.get'))

        if (self.name in self.BUILTIN_FNS
                and name == '__get__'):
            return Result(EMethod(NativeFunction(
                self._get, 'ebuiltin.__get__'), bound_self=self))

        if (self.name in self.BUILTIN_FNS
                and name == '__call__'):
            return Result(self)

        if self.name == 'object':
            if name == '__new__':
                return Result(get_guest_builtin('object.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('object.__init__'))
            if name == '__str__':
                return Result(get_guest_builtin('object.__str__'))
            if name == '__repr__':
                return Result(get_guest_builtin('object.__repr__'))
            if name == '__format__':
                return Result(get_guest_builtin('object.__format__'))
            if name == '__reduce_ex__':
                return Result(get_guest_builtin('object.__reduce_ex__'))
            if name == '__subclasshook__':
                return Result(get_guest_builtin('object.__subclasshook__'))
            if name == '__bases__':
                return Result(())
            if name == '__dict__':  # Fake it for now.
                return Result({})
            if name == '__setattr__':
                return Result(get_guest_builtin('object.__setattr__'))

        if self.name == 'type':
            if name == '__new__':
                return Result(get_guest_builtin('type.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('type.__init__'))
            if name == '__name__':
                return Result(get_guest_builtin('type.__name__'))
            if name == '__repr__':
                return Result(get_guest_builtin('type.__repr__'))
            if name == '__call__':
                return Result(get_guest_builtin('type.__call__'))
            if name == '__str__':
                return Result(get_guest_builtin('type.__str__'))
            if name == '__subclasses__':
                return Result(get_guest_builtin('type.__subclasses__'))
            if name == 'mro':
                return Result(get_guest_builtin('type.mro'))
            if name == '__dict__':  # Fake it for now.
                return Result({})

        if name == '__eq__':
            return Result(get_guest_builtin('object.__eq__'))
        if name == '__ne__':
            return Result(get_guest_builtin('object.__ne__'))

        if self.name in self.BUILTIN_TYPES:
            if name == '__mro__':
                return Result(self.get_mro())
            if name == '__dict__':  # Fake it for now.
                return Result({})

        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


@memoize
def get_guest_builtin(name: Text) -> EBuiltin:
    return EBuiltin(name, None)


def get_guest_builtin_self(name: Text, self: Any) -> EBuiltin:
    return EBuiltin(name, self)


class EPartial:
    def __init__(self, f: EFunction, args: Tuple[Any, ...]):
        assert isinstance(f, EFunction), f
        self.f = f
        self.args = args

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Any:
        return self.f.invoke(
            self.args + args, kwargs, locals_dict, ictx)


class NativeFunction(EPyObject):

    def __init__(self, f: Callable[..., Result], name: Text):
        self.f = f
        self.name = name

    def get_type(self) -> EPyObject:
        return EFunctionType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError

    @check_result
    def invoke(self, *args, **kwargs) -> Result[Any]:
        return self.f(*args, **kwargs)


###################
# Public functions

@check_result
def do_getitem(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    o, name = args
    if not isinstance(o, EPyObject):
        return Result(o[name])
    if o.hasattr('__getitem__'):
        f = o.getattr('__getitem__', ictx).get_value()
        return ictx.call(f, (args[1],), {}, {}, globals_=f.globals_)
    raise NotImplementedError(o, name)


@check_result
def do_setitem(args: Tuple[Any, ...], ictx: ICtx) -> Result[None]:
    assert len(args) == 3, args
    log('eo:do_setitem()', f'args: {args}')
    o, name, value = args
    if not isinstance(o, EPyObject):
        o[name] = value
        return Result(None)
    if o.hasattr('__setitem__'):
        f = o.getattr('__setitem__', ictx).get_value()
        res = ictx.call(f, (args[1], args[2]), {}, {}, globals_=f.globals_)
        if res.is_exception():
            return res
        return Result(None)
    raise NotImplementedError(o, name)


@check_result
def do_delitem(args: Tuple[Any, ...], ictx: ICtx) -> Result[None]:
    assert len(args) == 2, args
    log('eo:do_delitem()', f'args: {args}')
    o, name = args
    if not isinstance(o, EPyObject):
        del o[name]
        return Result(None)
    if o.hasattr('__delitem__'):
        f = o.getattr('__delitem__', ictx).get_value()
        res = ictx.call(f, (args[1],), {}, {}, globals_=f.globals_)
        if res.is_exception():
            return res
        return Result(None)
    raise NotImplementedError(o, name)


@check_result
def do_hasattr(args: Tuple[Any, ...], ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args
    o, attr = args
    assert isinstance(attr, str), attr

    if not isinstance(o, EPyObject):
        r = hasattr(o, attr)
        log('eo:hasattr()', f'{o}, {attr} => {r}')
        return Result(r)

    r = o.getattr(attr, ictx)
    log('eo:hasattr()', f'o {o} attr {attr!r} getattr result: {r}')
    if r.is_exception():
        if isinstance(r.get_exception().exception, AttributeError):
            return Result(False)
        return r

    return Result(True)


@check_result
def do_getattr(args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
    assert 2 <= len(args) <= 3, args
    assert not kwargs, kwargs
    o, attr, *default = args
    if type(o) is tuple and attr == '__class__':
        return Result(get_guest_builtin('tuple'))
    clsname = o.__class__.__name__
    if (type(o) in (int, str, tuple)
            and f'{clsname}.{attr}' in EBuiltin.BUILTIN_FNS):
        return Result(get_guest_builtin_self(f'{clsname}.{attr}', o))
    if not isinstance(o, EPyObject):
        try:
            a = getattr(o, attr, *default)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        else:
            return Result(a)
    if default and not o.hasattr(attr):
        return Result(default[0])
    return o.getattr(attr, ictx)


@check_result
def do_setattr(args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
    assert isinstance(args, tuple), args
    assert len(args) == 3, args
    assert not kwargs, kwargs
    obj, name, value = args
    if isinstance(obj, EPyObject):
        res = obj.setattr(name, value, ictx=ictx)
        if res.is_exception():
            return res
        return Result(None)
    elif obj is sys and name == 'path':
        sys.path = ictx.interp_state.paths = value
        return Result(None)
    else:
        raise NotImplementedError(obj, value)


@check_result
def do_dict(args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            ictx: ICtx) -> Result[Any]:
    f = get_guest_builtin('dict')
    return f.invoke(args, kwargs, {}, ictx)


@check_result
def do_tuple(args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    f = get_guest_builtin('tuple')
    return f.invoke(args, kwargs, {}, ictx)


@check_result
def invoke_desc(self, cls_attr: EPyObject, ictx: ICtx) -> Result[Any]:
    assert cls_attr.hasattr('__get__')

    # Grab the descriptor getter off the descriptor.
    f_result = cls_attr.getattr('__get__', ictx)
    if f_result.is_exception():
        return Result(f_result.get_exception())
    f = f_result.get_value()

    # Determine the type of obj.
    do_type = get_guest_builtin('type')
    objtype_result = do_type.invoke(args=(cls_attr,), kwargs={},
                                    locals_dict={}, ictx=ictx)
    if objtype_result.is_exception():
        return Result(objtype_result.get_exception())
    objtype = objtype_result.get_value()

    ictx.desc_count += 1

    return f.invoke((self, objtype), {}, {}, ictx)


@check_result
def do_iter(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 1

    if isinstance(args[0], _ITER_BUILTIN_TYPES):
        return Result(iter(args[0]))

    if isinstance(args[0], EPyObject) and args[0].hasattr('__iter__'):
        iter_f = args[0].getattr('__iter__', ictx)
        if iter_f.is_exception():
            return iter_f
        iter_f = iter_f.get_value()
        return iter_f.invoke((), {}, {}, ictx)

    if isinstance(args[0], EPyObject) and hasattr(args[0], 'iter'):
        return args[0].iter(ictx)

    raise NotImplementedError(args[0], type(args[0]))


TUPLE_ITERATOR = type(iter(()))
STR_ITERATOR = type(iter(''))
BYTES_ITERATOR = type(iter(b''))
LIST_ITERATOR = type(iter([]))
LIST_REV_ITERATOR = type(reversed([]))
DICT_ITERATOR = type(iter({}))
DICT_ITERATOR = type(iter(set([])))
DICT_KEY_ITERATOR = type(iter({}.keys()))
DICT_ITEM_ITERATOR = type(iter({}.items()))
RANGE_ITERATOR = type(iter(range(0)))
ZIP_ITERATOR = type(iter(zip((), ())))
BUILTIN_ITERATORS = (
    TUPLE_ITERATOR, LIST_ITERATOR, LIST_REV_ITERATOR, DICT_ITERATOR,
    RANGE_ITERATOR, DICT_KEY_ITERATOR, ZIP_ITERATOR, DICT_ITEM_ITERATOR,
    STR_ITERATOR, BYTES_ITERATOR,
    types.GeneratorType
)


@check_result
def do_next(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    g = args[0]
    if isinstance(g, BUILTIN_ITERATORS):
        try:
            return Result(next(g))
        except StopIteration as e:
            return Result(ExceptionData(None, None, e))
    if isinstance(g, EPyObject) and g.hasattr('__next__'):
        f = g.getattr('__next__', ictx)
        if f.is_exception():
            return f
        f = f.get_value()
        return f.invoke((), {}, {}, ictx)
    return g.next(ictx)

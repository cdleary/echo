"""(Metacircular) interpreter loop implementation."""

import dis
import types
import weakref

from typing import Dict, Any, Text, Tuple, List, Optional

from echo import epy_object
from echo import builtin_sys_module
from echo.epy_object import safer_repr
from echo.dso_objects import DsoFunctionProxy
from echo.common import get_code, none_filler
from echo.elog import log
from echo.interp_result import Result, ExceptionData, check_result
from echo.interp_context import ICtx
from echo import import_routines
from echo import arg_resolver
from echo import code_attributes
from echo.interpreter_state import InterpreterState
from echo.ecell import ECell
from echo.return_kind import ReturnKind
from echo.eobjects import (
    EFunction, EBuiltin, EPyObject, EClass, EMethod, EAsyncGenerator,
    get_guest_builtin, register_builtin,
)
from echo.enative_fn import ENativeFn
from echo import interp_routines
from echo.frame_objects import StatefulFrame, UnboundLocalSentinel
from echo.value import Value
from echo import ebuiltins

# These register builtins.
from echo.estaticmethod import EStaticMethod
from echo.eclassmethod import EClassMethod
from echo.egenerator import EGenerator
from echo.emodule import EModule
import echo.etraceback  # noqa: F401
import echo.emap
import echo.eproperty
import echo.builtin_build_class
import echo.builtin_dict
import echo.builtin_exception
import echo.builtin_int
import echo.builtin_iter
import echo.builtin_list
import echo.builtin_str
import echo.builtin_super
import echo.builtin_tuple
import echo.builtin_type
import echo.builtin_enumerate
import echo.builtin_predicates
import echo.builtin_object
import echo.builtin_bytearray
import echo.oo_builtins  # noqa: F401


@check_result
def interp(code: types.CodeType,
           *,
           globals_: Dict[Text, Any],
           ictx: ICtx,
           name: Text,
           locals_dict: Optional[Dict[Text, Any]] = None,
           args: Optional[Tuple[Any, ...]] = None,
           kwargs: Optional[Dict[Text, Any]] = None,
           defaults: Optional[Tuple[Any, ...]] = None,
           kwarg_defaults: Optional[Dict[Text, Any]] = None,
           closure: Optional[Tuple[ECell, ...]] = None,
           in_function: bool = True) -> Result[Any]:
    """Evaluates "code" using "globals_" after initializing locals with "args".

    Returns the result of evaluating the code object.

    Args:
        code: Code object to interpret.
        globals_: Global mapping to use (for global references).
        args: Arguments to populate local variables with (for a function
            invocation).
        defaults: Default arguments to use if the arguments haven't been
            populated via invocation.
        in_function: Whether this code is being interpreted at function scope;
            this controls whether generic "name" references resolve against
            globals (vs function locals).

    Implementation note: this is one giant function for the moment, unclear
    whether performance will be important, but this makes it easy for early
    prototyping.

    TODO(cdleary): 2019-01-21 Use dis.stack_effect to cross-check stack depth
        change.
    """
    log('interp', lambda: f'args: {args} kwargs: {kwargs}')

    closure = closure or ()

    assert len(code.co_freevars) == len(closure), (
        'Invocation did not satisfy closure requirements.', code,
        code.co_freevars, closure)

    def gprint(*args): interp_routines.cprint(*args, color='green')

    # Set up arguments as a precursor to establishing the locals.
    attrs = code_attributes.CodeAttributes.from_code(code, name)
    arg_result = arg_resolver.resolve_args(
        attrs, args, kwargs, defaults, kwarg_defaults)
    if arg_result.is_exception():
        return Result(arg_result.get_exception())

    arg_locals, additional_local_count = arg_result.get_value()

    locals_ = (arg_locals + [UnboundLocalSentinel] * additional_local_count)
    assert len(locals_) == attrs.nlocals, (len(locals_), attrs.nlocals)
    cellvars = tuple(ECell(name) for name in code.co_cellvars) + closure

    # Cellvars that match argument names get populated with the argument value,
    # and it seems as though locals_ for that value is never referenced in the
    # bytecode.
    for i, cellvar_name in enumerate(code.co_cellvars):
        try:
            index = code.co_varnames.index(cellvar_name)
        except ValueError:
            continue
        else:
            local_value = locals_[index]
            cellvars[i].set(local_value)

    instructions = tuple(dis.get_instructions(code))
    pc_to_instruction: List[Optional[dis.Instruction]] = \
        [None] * (instructions[-1].offset+1)
    pc_to_bc_width: List[Optional[int]] = [None] * (instructions[-1].offset+1)
    for i, instruction in enumerate(instructions):
        pc_to_instruction[instruction.offset] = instruction
        if i+1 != len(instructions):
            pc_to_bc_width[instruction.offset] = (
                instructions[i+1].offset-instruction.offset)
    del instructions

    f = StatefulFrame(code, pc_to_instruction, pc_to_bc_width, locals_,
                      locals_dict, globals_, cellvars, in_function, ictx)

    if attrs.generator:
        return Result(EGenerator(f))

    if attrs.async_generator:
        return Result(EAsyncGenerator(f))

    result = f.run_to_return_or_yield()
    if result.is_exception():
        return Result(result.get_exception())

    v, kind = result.get_value()
    assert kind == ReturnKind.RETURN, kind
    assert isinstance(v, Value), v
    return Result(v.wrapped)


def get_sunder_sre() -> types.ModuleType:
    return __import__('_sre')


@check_result
def _do_call_sre_compile(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]], ictx: ICtx) -> Result[Any]:
    """Helper for calling `_sre.compile`."""
    assert len(args) == 6 and not kwargs, (args, kwargs)
    pattern, flags, code, groups, groupindex, indexgroup = args
    new_code = []
    assert isinstance(code, list), code
    do_int = get_guest_builtin('int')
    for elem in code:
        coerced = do_int.invoke((elem,), {}, {}, ictx)
        if coerced.is_exception():
            return coerced
        new_code.append(coerced.get_value())
    try:
        _sre = get_sunder_sre()
        return Result(_sre.compile(pattern, flags, new_code, groups,
                                   groupindex, indexgroup))
    except Exception as e:
        return Result(ExceptionData(None, None, e))


@check_result
def do_call(f,
            args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            locals_dict: Dict[Text, Any],
            *,
            ictx: ICtx,
            globals_: Optional[Dict[Text, Any]] = None,
            in_function: bool = True
            ) -> Result[Any]:
    log('interp:do_call',
        lambda: f'f: {f} args: {safer_repr(args)} '
                f'kwargs: {safer_repr(kwargs)}')

    if ictx.call_profiler:
        ictx.call_profiler.note(f, args, kwargs)

    assert in_function

    kwargs = kwargs or {}
    if f in (dict, chr, range, print, sorted, str, set, tuple, hasattr,
             bytearray, object, frozenset, weakref.WeakSet,
             weakref.ref) + interp_routines.BUILTIN_EXCEPTION_TYPES:
        log('interp:do_call', f'f: {f} args: {args} kwargs: {kwargs}')
        r = f(*args, **kwargs)
        return Result(r)

    if f is globals:
        return Result(globals_)
    elif f is get_sunder_sre().compile:
        return _do_call_sre_compile(args, kwargs, ictx)
    elif type(f) in (EFunction, EMethod, EClassMethod, EStaticMethod,
                     ENativeFn, DsoFunctionProxy, EClass, EBuiltin):
        return f.invoke(args, kwargs, locals_dict, ictx, globals_=globals_)
    elif issubclass(type(f), EPyObject) and f.hasattr('__call__'):
        f_call = f.getattr('__call__', ictx)
        if f_call.is_exception():
            return f_call
        f_call = f_call.get_value()
        return f_call.invoke(args, kwargs, locals_dict, ictx,
                             globals_=globals_)
    elif not isinstance(f, EPyObject) and callable(f):
        log('interp:do_call:native',
            lambda: f'f: {f} args: {args} kwargs: {kwargs}')
        with epy_object.establish_ictx(locals_dict, globals_, ictx):
            return Result(f(*args, **kwargs))  # Native call.
    else:
        if isinstance(f, EPyObject):
            type_name = f.get_type().get_name()
        else:
            type_name = type(f).__name__
        return Result(ExceptionData(
            None, None,
            TypeError(f"'{type_name}' object {f} is not callable")))


def run_function(f: types.FunctionType, *args: Tuple[Any, ...],
                 builtins: Optional[EModule] = None,
                 globals_: Optional[Dict[Text, Any]] = None) -> Any:
    """Interprets f in the echo interpreter, returns unwrapped result."""
    state = InterpreterState(script_directory=None)
    globals_ = globals_ or {}
    builtins = builtins or EModule(
        'builtins', filename='<built-in>', globals_=ebuiltins.make_ebuiltins())
    esys = builtin_sys_module.make_sys_module(())
    ictx = ICtx(state, interp, do_call, builtins, esys)
    result = interp(get_code(f), globals_=globals_, defaults=f.__defaults__,
                    args=args, name=f.__name__, ictx=ictx)
    return result.get_value()


def import_path(path: Text, module_name: Text, fully_qualified_name: Text,
                ictx: ICtx) -> Result[import_routines.ModuleT]:
    result = import_routines.import_path(
        path, module_name, fully_qualified_name, ictx)
    return result


@check_result
@register_builtin('exec')
def _do_exec(args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[None]:
    assert 1 <= len(args) <= 3 and not kwargs, (args, kwargs)
    source, globals_, locals_ = none_filler(args, 3)
    if isinstance(source, types.CodeType):
        code = source
    else:
        assert isinstance(source, str), type(source)
        code = compile(source, 'exec-source', 'exec')
    res = interp(code, globals_=globals_, ictx=ictx, name='exec',
                 locals_dict=locals, in_function=False)
    if res.is_exception():
        return res
    return Result(None)

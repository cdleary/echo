import dis
import itertools
import functools
import operator
import os
import sys
import types
from typing import (
    List, Any, Text, Optional, Dict, Tuple, Callable, cast, Sequence, Union,
    Type,
)
from enum import Enum

from echo import iteration_helpers
from echo.elog import log
from echo.interp_context import ICtx
from echo import import_routines
from echo import etraceback
from echo.epy_object import EPyType, AttrWhere
from echo.eobjects import (
    ReturnKind, EBuiltin, EFunction, EPyObject,
    GuestCoroutine, EInstance, get_guest_builtin,
    do_getitem, do_setitem, do_hasattr, do_getattr,
    do_delitem, do_setattr, E_PREFIX, safer_repr,
)
from echo import trace_util
from echo.ecell import ECell
from echo.emodule import EModule
from echo.code_attributes import CodeAttributes
from echo.interpreter_state import InterpreterState
from echo.interp_result import Result, ExceptionData
from echo import interp_routines
from echo import bytecode_trace
from echo.value import Value


DEBUG_PRINT_BYTECODE_LINE = bool(os.getenv('DEBUG_PRINT_BYTECODE_LINE', False))
GUEST_BUILTINS = {
    list: {'append', 'remove', 'insert'},
    dict: {'keys', 'values', 'items', 'update'},
    str: {'format', 'join'},
}
opcodeno = 0


class WhyStatus(Enum):
    NOT = 0x01        # No error.
    EXCEPTION = 0x02  # Exception occurred.
    RETURN = 0x08     # 'return' statement.
    BREAK = 0x10      # 'break' statement.
    CONTINUE = 0x20   # 'continue' statement.
    YIELD = 0x40      # 'yield' operator.
    SILENCED = 0x80   # Exception silenced by 'with'.


# Use a sentinel value (this class object) to indicate when
# UnboundLocalErrors have occurred.
class UnboundLocalSentinel:
    pass


class _Sentinel:
    pass


AnyOrSentinel = Union[Any, Type[_Sentinel]]


# For nulls that appear in the CPython stack we push a sentinel value that
# means the same thing.
class StackNullSentinel:
    def __repr__(self):
        return '<null>'


# Indicates we should not push the result of executing some bytecode onto the
# stack, but allows us to use our normal result type for signaling errors.
class NoStackPushSentinel:
    pass


class BlockKind(Enum):
    EXCEPT_HANDLER = 'EXCEPT_HANDLER'
    SETUP_LOOP = 'SETUP_LOOP'
    SETUP_EXCEPT = 'SETUP_EXCEPT'
    SETUP_FINALLY = 'SETUP_FINALLY'


class BlockInfo:
    def __init__(self, kind: BlockKind, handler: int, level: int):
        self.kind = kind
        self.handler = handler
        self.level = level

    def __repr__(self) -> Text:
        return 'BlockInfo(kind={!r}, handler={!r}, level={!r})'.format(
            self.kind, self.handler, self.level)

    def to_trace(self) -> bytecode_trace.BlockStackEntry:
        return bytecode_trace.BlockStackEntry(self.kind.value, self.handler,
                                              self.level)


def wrap_with_push(frame: 'StatefulFrame', state: InterpreterState,
                   f: Callable) -> Callable:
    @functools.wraps(f)
    def push_wrapper(*args, **kwargs):
        prior = state.last_frame
        if isinstance(prior, StatefulFrame):
            frame.older_frame = prior
        state.last_frame = frame
        try:
            return f(*args, **kwargs, ictx=frame.ictx)
        finally:
            state.last_frame = prior

    return push_wrapper


class StatefulFrame:
    """A frame is the context in which some code executes.

    This StatefulFrame keeps track of the execution context for a piece of
    code; this is useful for frames that do not run to completion; e.g.
    generators, which may yield to the counter from some program counter and
    are subsequently available available to resume later.
    """

    def __init__(self,
                 code: types.CodeType,
                 pc_to_instruction: List[Optional[dis.Instruction]],
                 pc_to_bc_width: List[Optional[int]],
                 locals_: List[Any],
                 locals_dict: Optional[Dict[Text, Any]],
                 globals_: Dict[Text, Any],
                 cellvars: Tuple[ECell, ...],
                 in_function: bool,
                 ictx: ICtx):
        assert len(locals_) == len(code.co_varnames), \
            (len(locals_), len(code.co_varnames))
        self.code = code
        self.pc = 0
        self.stack = []
        self.block_stack = []  # type: List[BlockInfo]
        self.pc_to_instruction = pc_to_instruction
        self.pc_to_bc_width = pc_to_bc_width
        self.locals_ = locals_
        self.locals_dict = locals_dict
        self.globals_ = globals_
        self.current_lineno = None  # type: Optional[int]
        self.older_frame = None  # type: Optional[StatefulFrame]
        self.cellvars = cellvars
        self.consts = code.co_consts
        self.names = code.co_names
        self.ictx = ictx
        self.in_function = in_function

        self.interp_callback = wrap_with_push(
            self, ictx.interp_state, ictx.interp_callback)
        self.do_call_callback = wrap_with_push(
            self, ictx.interp_state, ictx.do_call_callback)

    def get_locals_dict(self) -> Optional[Dict[Text, Any]]:
        if self.locals_dict is not None:
            return self.locals_dict
        if not self.in_function:
            return None
        return {self.code.co_varnames[i]: v
                for i, v in enumerate(self.locals_)}

    @property
    def interp_state(self):
        return self.ictx.interp_state

    def _etype(self, arg) -> Any:
        do_type = get_guest_builtin('type')
        return do_type.invoke((arg,), {}, {}, self.ictx).get_value()

    def _eissubclass(self, t0, t1) -> bool:
        do_issubclass = get_guest_builtin('issubclass')
        r = do_issubclass.invoke((t0, t1), {}, {}, self.ictx).get_value()
        assert isinstance(r, bool)
        return r

    def _eisinstance(self, o, t) -> bool:
        do_issubclass = get_guest_builtin('isinstance')
        r = do_issubclass.invoke((o, t), {}, {}, self.ictx).get_value()
        assert isinstance(r, bool)
        log('fo:eii', f'o {safer_repr(o)} t {safer_repr(t)} => {r}')
        return r

    def _unwind_except_handler(self, b: BlockInfo) -> None:
        assert b.kind == BlockKind.EXCEPT_HANDLER, b
        while len(self.stack) > b.level+3:
            self._pop()
        ty = self._pop()
        val = self._pop()
        tb = self._pop()
        if val is StackNullSentinel:
            exception_data = None
        else:
            exception_data = ExceptionData(parameter=ty, exception=val,
                                           traceback=tb)
        log('fo:ueh', f'new exception data: {exception_data}')
        self.ictx.exc_info = exception_data

    def _unwind_block(self, b: BlockInfo) -> None:
        while len(self.stack) > b.level:
            self._pop()

    def _push_exception_info(
            self, exception_data: Optional[ExceptionData]) -> None:
        if exception_data:
            log('fo:he', f'exc_info: {self.ictx.exc_info}')
            self._push(exception_data.traceback)
            self._push(exception_data.exception)
            self._push(self._etype(exception_data.exception))
        else:
            self._push(StackNullSentinel)
            self._push(StackNullSentinel)
            self._push(None)

    def _handle_exception(self, why: WhyStatus,
                          exception_data: Optional[ExceptionData],
                          return_value: AnyOrSentinel) -> bool:
        """Returns whether the exception was handled in this function.

        Side effects:
            When an exception is handled, the PC is set to that of the handler.
        """
        # Pop until we see an except block, or there's no block stack left.
        log('fo:he', f'handling exception; block stack: {self.block_stack}')
        while self.block_stack:
            if (why == WhyStatus.EXCEPTION
                    and self.block_stack[-1].kind in (
                        BlockKind.SETUP_EXCEPT, BlockKind.SETUP_FINALLY)):
                # We wound up at an except block, pop back to the right
                # value-stack depth and start running the handler.
                self.pc = self.block_stack[-1].handler
                self._unwind_block(self.block_stack[-1])
                self._push_exception_info(self.ictx.exc_info)
                self._push_exception_info(exception_data)
                # The block stack entry transmorgifies into an EXCEPT_HANDLER.
                self.block_stack[-1].kind = BlockKind.EXCEPT_HANDLER
                self.block_stack[-1].handler = -1
                self.ictx.exc_info = exception_data
                return True

            if (why == WhyStatus.CONTINUE and
                    self.block_stack[-1].kind == BlockKind.SETUP_LOOP):
                b = self.block_stack[-1]
                self.pc = return_value
                return True

            if self.block_stack[-1].kind == BlockKind.SETUP_FINALLY:
                b = self.block_stack.pop()
                self._unwind_block(b)
                # Not an exception, but we have a finally block to run.
                if why in (WhyStatus.RETURN, WhyStatus.CONTINUE):
                    assert return_value is not _Sentinel
                    self._push(return_value)
                self._push(why)
                self.pc = b.handler
                return True

            if self.block_stack[-1].kind == BlockKind.EXCEPT_HANDLER:
                self._unwind_except_handler(self.block_stack.pop())
                continue

            if self.block_stack[-1].kind == BlockKind.SETUP_LOOP:
                self._unwind_block(self.block_stack.pop())
                continue

            raise NotImplementedError(self.block_stack[-1])

        log('fo:he', 'extinguished block stack without setting PC')
        return False

    def _push(self, x: Any) -> None:
        assert not isinstance(x, Result), x
        # If the user can observe the real isinstance they can break the
        # virtualization abstraction, which is undesirable.
        assert x is not isinstance
        assert x is not tuple
        assert x is not dict
        assert x is not Exception
        assert x is not BaseException
        assert not isinstance(x, Value), x
        assert x is not GuestCoroutine
        log('fo:stack:push()', lambda: safer_repr(x))
        self.stack.append(x)

    def _push_value(self, x: Value) -> None:
        self._push(x.wrapped)

    def _pop(self) -> Any:
        x = self.stack.pop()
        log('fo:stack:pop()', lambda: safer_repr(x))
        return x

    def _pop_n(self, n: int, tos_is_0: bool = True) -> Tuple[Any, ...]:
        self.stack, result = (
            self.stack[:len(self.stack)-n], self.stack[len(self.stack)-n:])
        if tos_is_0:
            return tuple(reversed(result))
        return tuple(result)

    def _peek(self):
        return self.stack[-1]

    def _get_global_or_builtin(self, name: Text) -> Result[Any]:
        try:
            return Result(self.globals_[name])
        except KeyError:
            pass
        res = self.ictx.get_ebuiltins().getattr(name, self.ictx)
        if not res.is_exception():
            return res
        log('bc:globals', f'globals: {self.globals_.keys()}')
        return Result(ExceptionData(
            None, None, NameError(f'name {name!r} is not defined')))

    def _run_FORMAT_VALUE(self, arg, argval) -> Result[str]:
        fmt_spec = ''
        if (arg & 0x4) == 4:  # Pop fmt_spec from the stack and use it.
            fmt_spec = self._pop()

        value = self._pop()
        if (arg & 0x3) == 0:  # Value is formatted as-is.
            pass
        elif (arg & 0x3) == 1:  # Call str on value before formatting.
            s = get_guest_builtin('str')
            res = s.invoke((value,), {}, {}, self.ictx)
            if res.is_exception():
                return res
            value = res.get_value()
        elif (arg & 0x3) == 2:  # Call repr on value before formatting.
            s = get_guest_builtin('repr')
            res = s.invoke((value,), {}, {}, self.ictx)
            if res.is_exception():
                return res
            value = res.get_value()

        return Result(format(value, fmt_spec))

    def _run_BUILD_STRING(self, arg, argval) -> Result[str]:
        pieces = self._pop_n(arg, tos_is_0=False)
        return Result(''.join(pieces))

    def _run_POP_TOP(self, arg, argval):
        self._pop()

    def _run_LIST_APPEND(self, arg, argval):
        tos = self._pop()
        tos_mi = self.stack[-arg]
        list.append(tos_mi, tos)

    def _run_SET_ADD(self, arg, argval):
        tos = self._pop()
        tos_mi = self.stack[-arg]
        set.add(tos_mi, tos)

    def _run_POP_BLOCK(self, arg, argval):
        self.block_stack.pop()

    def _run_DELETE_SUBSCR(self, arg, argval):
        tos = self._pop()
        tos1 = self._pop()
        if isinstance(tos1, (dict, list, type(os.environ))):
            try:
                del tos1[tos]
            except KeyError as e:
                return Result(ExceptionData(None, None, e))
        elif isinstance(tos1, EPyObject):
            r = do_delitem((tos1, tos), self.ictx)
            assert not r.is_exception(), r
        else:
            raise NotImplementedError(tos, tos1)

    def _run_LOAD_CONST(self, arg, argval):
        return Result(self.consts[arg])

    def _run_GET_ITER(self, arg, argval) -> Result[Any]:
        do_iter = get_guest_builtin('iter')
        return do_iter.invoke((self._pop(),), {}, {}, self.ictx)

    def _run_LOAD_BUILD_CLASS(self, arg, argval):
        return Result(get_guest_builtin('__build_class__'))

    def _run_BUILD_TUPLE(self, arg, argval):
        count = arg
        t = self._pop_n(count, tos_is_0=False)
        return Result(t)

    def _run_BUILD_TUPLE_UNPACK(self, arg, argval) -> Result[Any]:
        iterables = self._pop_n(arg, tos_is_0=False)
        return Result(tuple(itertools.chain(*iterables)))

    def _run_BUILD_TUPLE_UNPACK_WITH_CALL(self, arg, argval) -> Result[Any]:
        return self._run_BUILD_TUPLE_UNPACK(arg, argval)

    def _run_BUILD_LIST(self, arg, argval):
        count = arg
        limit = len(self.stack)-count
        self.stack, t = self.stack[:limit], self.stack[limit:]
        return Result(t)

    def _run_BUILD_MAP(self, arg, argval):
        items = self._pop_n(2 * arg, tos_is_0=False)
        ks = items[::2]
        vs = items[1::2]
        return Result(dict(zip(ks, vs)))

    def _run_MAP_ADD(self, arg, argval) -> None:
        k = self._pop()
        v = self._pop()
        map_ = self.stack[-arg]
        assert isinstance(map_, dict), map_
        si = get_guest_builtin('dict.__setitem__')
        si.invoke((map_, k, v), {}, {}, self.ictx)

    def _run_BUILD_SET(self, arg, argval):
        count = arg
        limit = len(self.stack)-count
        self.stack, t = self.stack[:limit], self.stack[limit:]
        return Result(set(t))

    def _run_BUILD_SLICE(self, arg, argval):
        step = self._pop() if arg == 3 else None
        stop = self._pop()
        start = self._pop()
        return Result(slice(start, stop, step))

    def _run_BUILD_CONST_KEY_MAP(self, arg, argval):
        count = arg
        ks = self._pop()
        self.stack, vs = self.stack[:-count], tuple(self.stack[-count:])
        assert len(ks) == len(vs)
        return Result(dict(zip(ks, vs)))

    def _run_ROT_TWO(self, arg, argval):
        self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]

    def _run_DUP_TOP(self, arg, argval):
        assert self.stack, 'Cannot DUP_TOP of empty stack.'
        self.stack = self.stack + self.stack[-1:]

    def _run_POP_EXCEPT(self, arg, argval):
        self._unwind_except_handler(self.block_stack.pop())

    def _run_SETUP_FINALLY(self, arg, argval):
        # "Pushes a try block from a try-except clause onto the block stack.
        # delta points to the finally block."
        # -- https://docs.python.org/3.7/library/dis.html#opcode-SETUP_FINALLY
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_FINALLY, arg+self.pc+self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_DELETE_NAME(self, arg, argval):
        log('fo:dn', f'argval: {argval} code.co_names: {self.code.co_names} '
                     f'locals: {self.locals_} globals: {self.globals_}')
        if self.in_function:
            if self.locals_dict is not None:
                del self.locals_dict[argval]
            else:
                self.locals_[arg] = UnboundLocalSentinel
        else:
            del self.globals_[argval]

    def _run_DUP_TOP_TWO(self, arg, argval):
        self.stack = self.stack + self.stack[-2:]

    def _run_ROT_THREE(self, arg, argval):
        #                                  old first  old second  old third
        self.stack[-3], self.stack[-1], self.stack[-2] = (
            self.stack[-1], self.stack[-2], self.stack[-3])

    def _run_LOAD_DEREF(self, arg, argval):
        return Result(self.cellvars[arg].get())

    def _run_STORE_DEREF(self, arg, argval):
        self.cellvars[arg].set(self._pop())

    def _run_STORE_FAST(self, arg, argval):
        self.locals_[arg] = self._pop()

    def _run_LOAD_CLOSURE(self, arg, argval):
        return Result(self.cellvars[arg])

    def sets_pc(f):
        f._sets_pc = True
        return f

    def _run_SETUP_WITH(self, arg, argval) -> Result[Any]:
        mgr = self._peek()
        do_getattr = get_guest_builtin('getattr')
        enter = do_getattr.invoke((mgr, '__enter__'), {}, {}, self.ictx)
        if enter.is_exception():
            return enter
        enter = enter.get_value()
        exit = do_getattr.invoke((mgr, '__exit__'), {}, {}, self.ictx)
        if exit.is_exception():
            return exit
        exit = exit.get_value()
        self._pop()
        self._push(exit)
        res = self.ictx.call(enter, (), {}, {})
        if res.is_exception():
            return res
        self._run_SETUP_FINALLY(arg, argval)
        return Result(res.get_value())

    def _run_WITH_CLEANUP_START(self, arg, argval) -> Result[Any]:
        exc = self._peek()
        log('fo:wcs', f'exc: {exc!r}')
        val = tb = None
        if exc is None:
            self._pop()
            exit_func = self._pop()
            self._push(None)
        elif isinstance(exc, int):
            self._pop()
            raise NotImplementedError
        else:
            val, tb, tp2, exc2, tb2 = reversed(self.stack[-6:-1])
            log('fo:wcs', f'val: {val!r} tb: {tb!r} stack: {self.stack}')
            exit_func = self.stack[-7]
            self.stack[-7] = tb2
            self.stack[-6] = exc2
            self.stack[-5] = tp2
            self.stack[-4] = StackNullSentinel
            self.block_stack[-1].level -= 1

        assert tb is not StackNullSentinel
        res = self.ictx.call(exit_func, (exc, val, tb), {}, {})
        if res.is_exception():
            return res
        self._push(exc)
        return res

    def _run_WITH_CLEANUP_FINISH(self, arg, argval) -> None:
        res = self._pop()
        exc = self._pop()
        if res is True:
            self._push(WhyStatus.SILENCED)
        elif res is None:
            pass
        else:
            raise NotImplementedError

    @sets_pc
    def _run_BREAK_LOOP(self, arg, argval):
        loop_block = self.block_stack.pop()
        assert loop_block.kind == BlockKind.SETUP_LOOP
        while len(self.stack) > loop_block.level:
            self._pop()
        self.pc = loop_block.handler
        return True

    @sets_pc
    def _run_JUMP_ABSOLUTE(self, arg, argval):
        self.pc = arg
        return True

    @sets_pc
    def _run_JUMP_FORWARD(self, arg, argval):
        self.pc += arg + self.pc_to_bc_width[self.pc]
        return True

    def _is_truthy(self, o: Any) -> Result[bool]:
        do_bool = get_guest_builtin('bool')
        return do_bool.invoke((o,), {}, {}, self.ictx)

    def _is_falsy(self, o: Any) -> Result[bool]:
        res = self._is_truthy(o)
        if res.is_exception():
            return res
        v = res.get_value()
        assert isinstance(v, bool), v
        return Result(not v)

    @sets_pc
    def _run_POP_JUMP_IF_FALSE(self, arg, argval):
        v = self._pop()
        if self._is_falsy(v).get_value():
            log('bc:pjif', f'jumping on falsy: {v}')
            self.pc = arg
            return True
        log('bc:pjif', f'not jumping, truthy: {v}')
        return False

    @sets_pc
    def _run_POP_JUMP_IF_TRUE(self, arg, argval):
        v = self._pop()
        if self._is_truthy(v).get_value():
            log('bc:pjit', f'jumping on truthy: {v}')
            self.pc = arg
            return True
        log('bc:pjit', f'not jumping, falsy: {v}')
        return False

    @sets_pc
    def _run_JUMP_IF_FALSE_OR_POP(self, arg, argval):
        if self._is_falsy(self._peek()).get_value():
            self.pc = arg
            return True
        else:
            self._pop()
            return False

    @sets_pc
    def _run_JUMP_IF_TRUE_OR_POP(
            self, arg, argval) -> Union[bool, Result[Any]]:
        res = self._is_truthy(self._peek())
        if res.is_exception():
            return res
        if res.get_value():
            self.pc = arg
            return True
        else:
            self._pop()
            return False

    @sets_pc
    def _run_FOR_ITER(self, arg, argval):
        o = self._peek()
        do_next = get_guest_builtin('next')
        r = do_next.invoke((o,), {}, {}, self.ictx)
        log('bc:for_iter', f'o: {o} r: {r}')
        if (r.is_exception()
                and isinstance(r.get_exception().exception, StopIteration)):
            self._pop()
            self.pc += self.pc_to_bc_width[self.pc] + arg
            new_instruction = self.pc_to_instruction[self.pc]
            assert new_instruction is not None
            assert new_instruction.is_jump_target, (
                'Attempted to jump to invalid target.', self.pc,
                self.pc_to_instruction[self.pc])
            return True

        assert not r.is_exception(), r
        self._push(r.get_value())

    def _run_MAKE_FUNCTION(self, arg, argval):
        if sys.version_info >= (3, 6):
            qualified_name = self._pop()
            code = self._pop()
            freevar_cells = self._pop() if arg & 0x08 else None
            annotation_dict = self._pop() if arg & 0x04 else None
            kwarg_defaults = self._pop() if arg & 0x02 else None
            positional_defaults = self._pop() if arg & 0x01 else None
            if annotation_dict:
                # TODO(cdleary): 2019-10-26 We just ignore this for now.
                # raise NotImplementedError(annotation_dict)
                pass
        else:
            # 3.5 documentation:
            # https://docs.python.org/3.5/library/dis.html#opcode-MAKE_FUNCTION
            default_argc = arg & 0xff
            name_and_default_pairs = (arg >> 8) & 0xff
            annotation_objects = (arg >> 16) & 0x7fff
            if annotation_objects:
                raise NotImplementedError(annotation_objects)
            qualified_name = self._pop()
            code = self._pop()
            kwarg_default_items = self._pop_n(2 * name_and_default_pairs,
                                              tos_is_0=False)
            kwarg_defaults = dict(zip(kwarg_default_items[::2],
                                      kwarg_default_items[1::2]))
            positional_defaults = self._pop_n(default_argc, tos_is_0=False)
            freevar_cells = None

        f = EFunction(code, self.globals_, qualified_name,
                      defaults=positional_defaults,
                      kwarg_defaults=kwarg_defaults,
                      closure=freevar_cells)
        return Result(f)

    def _run_CALL_FUNCTION(self, arg, argval):
        # https://docs.python.org/3.7/library/dis.html#opcode-CALL_FUNCTION
        #
        # Note: As of Python 3.6 this only supports calls for functions with
        # positional arguments.
        if sys.version_info >= (3, 6):
            argc = arg
            kwargc = 0
        else:
            argc = arg & 0xff
            kwargc = arg >> 8
        kwarg_stack = self._pop_n(2 * kwargc, tos_is_0=False)
        kwargs = dict(zip(kwarg_stack[::2], kwarg_stack[1::2]))
        args = self._pop_n(argc, tos_is_0=False)
        f = self._pop()
        log('bc:call',
            lambda: f'{self.code.co_filename}:{self.current_lineno} f: {f} '
                    f'args: {args}')
        result = self.do_call_callback(
            f, args, kwargs, locals_dict=self.get_locals_dict(),
            globals_=self.globals_)
        assert isinstance(result, Result), (result, f)
        return result

    def _run_STORE_NAME(self, arg, argval):
        if self.in_function:
            if self.locals_dict is not None:
                value = self._pop()
                res = do_setitem((self.locals_dict, argval, value), self.ictx)
                if res.is_exception():
                    raise NotImplementedError
            else:
                self.locals_[arg] = self._pop()
        else:
            v = self._pop()
            self.globals_[argval] = v

    def _run_STORE_ATTR(self, arg, argval) -> Result[Any]:
        obj = self._pop()
        value = self._pop()
        log('bc:sa', f'obj {obj!r} attr {argval!r} val {value!r}')
        r = do_setattr((obj, argval, value), {}, self.ictx)
        if r.is_exception():
            return r
        return Result(NoStackPushSentinel)

    def _run_STORE_GLOBAL(self, arg, argval) -> None:
        self.globals_[argval] = self._pop()

    def _run_MAKE_CLOSURE(self, arg, argval) -> Result[Any]:
        # Note: this bytecode was removed in Python 3.6.
        name = self._pop()
        code = self._pop()
        freevar_cells = self._pop()
        defaults = self._pop_n(arg)
        f = EFunction(code, self.globals_, name, defaults=defaults,
                      closure=freevar_cells)
        return Result(f)

    def _run_LOAD_FAST(self, arg, argval) -> Result[Any]:
        v = self.locals_[arg]
        if v is UnboundLocalSentinel:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(None, None, NameError(msg)))
        return Result(v)

    def _run_DELETE_FAST(self, arg, argval) -> None:
        self.locals_[arg] = UnboundLocalSentinel

    def _run_IMPORT_NAME(self, arg, argval):
        assert isinstance(argval, str), argval
        fromlist = self._pop()
        level = self._pop()
        return import_routines.run_IMPORT_NAME(
            self.code.co_filename, level, fromlist, argval, self.globals_,
            self.ictx)

    def _run_IMPORT_FROM(self, arg, argval):
        module = self._peek()
        return import_routines.run_IMPORT_FROM(
            module, argval, self.ictx)

    def _run_LOAD_GLOBAL(self, arg, argval):
        namei = arg
        name = self.names[namei]
        return self._get_global_or_builtin(name)

    def _run_LOAD_NAME(self, arg, argval):
        if self.in_function:
            if self.locals_dict is not None:
                try:
                    return do_getitem((self.locals_dict, argval), self.ictx)
                except KeyError:
                    pass
            else:
                return Result(self.locals_[arg])
        return self._get_global_or_builtin(argval)

    def _run_LOAD_ATTR(self, arg, argval) -> Result[Any]:
        obj = self._pop()
        log('bc:la', lambda: f'obj {obj!r} attr {argval}')
        if isinstance(obj, EInstance):
            r = obj.getattr(argval, self.ictx)
        elif isinstance(obj, EPyObject):
            r = obj.getattr(argval, self.ictx)
        elif obj is None and argval == '__new__':
            r = Result(get_guest_builtin('type.__new__'))
        elif obj is sys and argval == 'path':
            r = Result(self.interp_state.paths)
        elif obj is sys and argval == 'modules':
            r = Result(self.interp_state.sys_modules)
        else:
            r = do_getattr((obj, argval), {}, self.ictx)
        if not r.is_exception():
            assert do_hasattr((obj, argval), self.ictx).get_value() is True, \
                   (obj, argval)
        log('bc:la', lambda: f'obj {obj!r} attr {argval} => {r}')
        return r

    def _run_COMPARE_OP(self, arg, argval):
        rhs = self._pop()
        lhs = self._pop()
        if argval == 'exception match':
            return interp_routines.exception_match(lhs, rhs, self.ictx)
        else:
            return interp_routines.compare(
                argval, lhs, rhs, self.ictx)

    @sets_pc
    def _run_END_FINALLY(self, arg, argval) -> Result[bool]:
        status = self._pop()
        log('bc:ef', f'END_FINALLY status {status!r}')
        do_issubclass = get_guest_builtin('issubclass')
        if isinstance(status, (int, WhyStatus)):
            why = WhyStatus(status)

            if why == WhyStatus.SILENCED:
                self._unwind_except_handler(self.block_stack.pop())
                return Result(False)

            if why in (WhyStatus.CONTINUE, WhyStatus.RETURN):
                retval = self._pop()
                assert retval is not _Sentinel, retval
                assert self._handle_exception(why, None, retval)
                return Result(True)

            raise NotImplementedError(status)
        elif self._eissubclass(status, get_guest_builtin('BaseException')):
            exc = self._pop()
            tb = self._pop()
            exception_data = ExceptionData(traceback=tb, parameter=status,
                                           exception=exc)
            log('bc:ef', f'END_FINALLY exception_data {exception_data!r}')
            return Result(exception_data)
        elif status is None:
            return Result(False)
        else:
            raise NotImplementedError(repr(status))

    def _run_UNARY_NOT(self, arg, argval) -> None:
        arg = self._pop()
        self._push(self._is_falsy(arg).get_value())

    def _run_UNARY_INVERT(self, arg, argval) -> Result[Any]:
        arg = self._pop()
        return interp_routines.run_unop('UNARY_INVERT', arg, self.ictx)

    def _run_UNARY_NEGATIVE(self, arg, argval) -> Result[Any]:
        arg = self._pop()
        return interp_routines.run_unop('UNARY_NEGATIVE', arg, self.ictx)

    def _run_UNARY_POSITIVE(self, arg, argval) -> Result[Any]:
        arg = self._pop()
        return interp_routines.run_unop('UNARY_POSITIVE', arg, self.ictx)

    def _run_binary(self, opname) -> Result[Any]:
        rhs = self._pop()
        lhs = self._pop()
        return interp_routines.run_binop(
            opname, lhs, rhs, self.ictx)

    def _run_BINARY_ADD(self, arg, argval):
        return self._run_binary('BINARY_ADD')

    def _run_BINARY_OR(self, arg, argval):
        return self._run_binary('BINARY_OR')

    def _run_BINARY_AND(self, arg, argval):
        return self._run_binary('BINARY_AND')

    def _run_BINARY_LSHIFT(self, arg, argval):
        return self._run_binary('BINARY_LSHIFT')

    def _run_BINARY_RSHIFT(self, arg, argval):
        return self._run_binary('BINARY_RSHIFT')

    def _run_BINARY_SUBTRACT(self, arg, argval):
        return self._run_binary('BINARY_SUBTRACT')

    def _run_BINARY_SUBSCR(self, arg, argval):
        return self._run_binary('BINARY_SUBSCR')

    def _run_BINARY_MULTIPLY(self, arg, argval):
        return self._run_binary('BINARY_MULTIPLY')

    def _run_BINARY_MODULO(self, arg, argval):
        return self._run_binary('BINARY_MODULO')

    def _run_BINARY_TRUE_DIVIDE(self, arg, argval):
        return self._run_binary('BINARY_TRUE_DIVIDE')

    def _run_BINARY_FLOOR_DIVIDE(self, arg, argval):
        return self._run_binary('BINARY_FLOOR_DIVIDE')

    def _run_INPLACE(self, subopcode: Text, arg, argval) -> Result[Any]:
        rhs = self._pop()
        lhs = self._pop()
        if ({type(lhs), type(rhs)} <=
                interp_routines.BUILTIN_VALUE_TYPES | {list}):
            return interp_routines.run_binop(
                'BINARY_' + subopcode, lhs, rhs, self.ictx)
        else:
            raise NotImplementedError(lhs, rhs)

    def _run_INPLACE_OR(self, arg, argval):
        return self._run_INPLACE('OR', arg, argval)

    def _run_INPLACE_AND(self, arg, argval):
        return self._run_INPLACE('AND', arg, argval)

    def _run_INPLACE_ADD(self, arg, argval):
        return self._run_INPLACE('ADD', arg, argval)

    def _run_INPLACE_SUBTRACT(self, arg, argval):
        return self._run_INPLACE('SUBTRACT', arg, argval)

    def _run_SETUP_EXCEPT(self, arg, argval):
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_EXCEPT, arg+self.pc+self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_STORE_SUBSCR(self, arg, argval) -> Result[Any]:
        tos = self._pop()
        tos1 = self._pop()
        tos2 = self._pop()
        r = do_setitem((tos1, tos, tos2), self.ictx)
        if r.is_exception():
            return r
        return Result(NoStackPushSentinel)

    def _run_CALL_FUNCTION_KW(self, arg, argval):
        args = arg
        kwarg_names = self._pop()
        kwarg_values = self._pop_n(len(kwarg_names), tos_is_0=False)
        assert len(kwarg_names) == len(kwarg_values), (
            kwarg_names, kwarg_values)
        kwargs = dict(zip(kwarg_names, kwarg_values))
        rest = args-len(kwargs)
        args = self._pop_n(rest, tos_is_0=False)
        to_call = self._pop()
        return self.do_call_callback(
            to_call, args, kwargs, self.locals_dict,
            globals_=self.globals_)

    def _run_SETUP_LOOP(self, arg, argval):
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_LOOP, arg + self.pc + self.pc_to_bc_width[self.pc],
            len(self.stack)))

    @sets_pc
    def _run_CONTINUE_LOOP(self, arg, argval) -> bool:
        assert self._handle_exception(WhyStatus.CONTINUE, None, arg)
        return True

    def _run_RAISE_VARARGS(self, arg, argval):
        argc = arg
        cause, exc = _Sentinel, _Sentinel
        if argc >= 2:
            cause = self._pop()
        if argc >= 1:
            exc = self._pop()
        if exc is _Sentinel:  # Re-raise.
            return Result(self.ictx.exc_info)

        log('bc:rv', f'RAISE_VARARGS exc {safer_repr(exc)}')
        if (isinstance(exc, type) and issubclass(exc, BaseException)):
            ty = exc
            exc = ty()
        elif self._eisinstance(exc, get_guest_builtin('BaseException')):
            ty = self._etype(exc)
        else:
            ty = TypeError
            exc = TypeError('exception must derive from BaseException')

        return Result(ExceptionData([], ty, exc))

    def _run_LOAD_METHOD(self, arg, argval):
        # Note: New in 3.7. See also _run_CALL_METHOD
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-LOAD_METHOD
        obj = self._peek()
        desc_count_before = self.ictx.desc_count
        attr_result = self._run_LOAD_ATTR(arg, argval)
        if attr_result.is_exception():
            return attr_result
        log('bc:lm', f'LOAD_ATTR obj {obj!r} argval {argval} => {attr_result}')
        if (desc_count_before == self.ictx.desc_count
                and interp_routines.method_requires_self(
                    obj=obj, name=argval, value=attr_result.get_value())):
            self._push(obj)
        else:
            self._push(StackNullSentinel)
        self._push(attr_result.get_value())

    def _run_CALL_METHOD(self, arg, argval):
        # Note: new in 3.7. See also _run_LOAD_METHOD
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-CALL_METHOD
        positional_argc = arg
        args = self._pop_n(positional_argc, tos_is_0=False)
        method = self._pop()
        self_value = self._pop()
        if self_value is not StackNullSentinel:
            args = (self_value,) + args
        log('bc:cm', lambda: f'method: {method}')
        log('bc:cm', lambda: f'args: {args}')
        log('bc:cm', lambda: f'self_value: {self_value}')
        return self.do_call_callback(
            method, args, {}, self.locals_dict,
            globals_=self.globals_)

    def _run_CALL_FUNCTION_EX(self, arg, argval):
        if arg & 0x1:
            kwargs = self._pop()
        else:
            kwargs = None
        callargs = self._pop()
        if not isinstance(callargs, tuple):
            do_tuple = get_guest_builtin('tuple')
            callargs = do_tuple.invoke((callargs,), {}, {}, self.ictx)
            if callargs.is_exception():
                return callargs
            callargs = callargs.get_value()
        func = self._pop()
        return self.do_call_callback(
            func, callargs, kwargs, self.locals_dict, globals_=self.globals_)

    def _run_PRINT_EXPR(self, arg, argval):
        value = self._pop()
        if value is not None:
            if isinstance(value, EPyObject):
                r = value.getattr('__repr__', self.ictx)
                s = self.do_call_callback(
                    r, (), {}, self.locals_dict, globals_=r.globals_)
                print(s)
            else:
                print(repr(value))

    def _run_IMPORT_STAR(self, arg, argval):
        module = self._peek()
        import_routines.import_star(module, self.globals_, self.ictx)
        self._pop()  # Docs say 'module is popped after loading all names'.

    def _run_UNPACK_EX(self, arg, argval):
        tos = self._pop()
        do_iter = get_guest_builtin('iter')
        it = do_iter.invoke((tos,), {}, {}, self.ictx)
        if it.is_exception():
            return it
        it = it.get_value()
        stack_values = []
        do_next = get_guest_builtin('next')
        for _ in range(arg):
            r = do_next.invoke((it,), {}, {}, self.ictx)
            if r.is_exception():
                return r
            stack_values.append(r.get_value())
        rest = []
        while True:
            r = do_next.invoke((it,), {}, {}, self.ictx)
            if (r.is_exception()
                    and isinstance(r.get_exception().exception,
                                   StopIteration)):
                break
            if r.is_exception():
                return r
            rest.append(r.get_value())
        stack_values.append(rest)
        for item in reversed(stack_values):
            self._push(item)

    def _run_UNPACK_SEQUENCE(self, arg, argval) -> Optional[Result[None]]:
        # https://docs.python.org/3.7/library/dis.html#opcode-UNPACK_SEQUENCE
        t = self._pop()

        seen = []

        def cb(item: Any) -> Result[bool]:
            seen.append(item)
            return Result(True)

        res = iteration_helpers.foreach(t, cb, self.ictx)
        if res.is_exception():
            return res

        for item in reversed(seen):
            self._push(item)

    def _run_EXTENDED_ARG(self, arg, argval):
        pass  # The to-instruction decoding step already extended the args?

    def _dump_inst(self, instruction: dis.Instruction) -> None:
        global opcodeno
        if instruction.starts_line:
            print(f'{self.code.co_filename}:{instruction.starts_line}'
                  f' :: {self.code.co_name}',
                  file=sys.stderr)
        if os.getenv('ECHO_DUMP_INSTS') == 'lines':
            return
        print('{:5d} :: {:3d} {}'.format(
            opcodeno,
            instruction.offset,
            trace_util.remove_at_hex(str(instruction))), file=sys.stderr)
        opcodeno += 1
        if (instruction.opname == 'EXTENDED_ARG' or
                os.getenv('ECHO_DUMP_INSTS') == 'nostack'):
            return
        print(' ' * 8, ' stack ({}):{}'.format(len(self.stack),
              ' empty' if len(self.stack) == 0 else ''), file=sys.stderr)
        for i, item in enumerate(reversed(self.stack)):
            item_type = self._etype(item)
            if (isinstance(item, EPyObject) or
                    isinstance(item, (types.FunctionType,
                                      types.BuiltinFunctionType, type, bool,
                                      int))):
                s = '{!r} :: {}'.format(
                    item_type, trace_util.remove_at_hex(repr(item)))
            else:
                s = repr(item_type)
            if item is StackNullSentinel:
                s = '<null>'
            print(' ' * 8, '  TOS{}: {}'.format(i, s), file=sys.stderr)

        if self.block_stack:
            print(' ' * 8, 'f_iblock: {}'.format(len(self.block_stack)),
                  file=sys.stderr)
            for i, block_info in enumerate(self.block_stack):
                print(' ' * 9,
                      'blockstack {}: type: {} handler: {} level: {}'
                      .format(
                        i, block_info.kind.value, block_info.handler,
                        block_info.level), file=sys.stderr)

    def _run_one_bytecode(self) -> Optional[Result[Tuple[Value, ReturnKind]]]:
        instruction = self.pc_to_instruction[self.pc]
        assert instruction is not None

        if instruction.starts_line:
            self.current_lineno = instruction.starts_line
            log('bc:line',
                f'{self.code.co_filename}:{instruction.starts_line}')

        log('bc:inst', instruction)
        if os.getenv('ECHO_DUMP_INSTS'):
            self._dump_inst(instruction)

        if instruction.starts_line is not None:
            self.line = instruction.starts_line

        if instruction.opname == 'RETURN_VALUE':
            v = Value(self._pop())
            log('bc:rv', repr(v))
            return Result((v, ReturnKind.RETURN))

        if instruction.opname == 'YIELD_VALUE':
            self.pc += self.pc_to_bc_width[self.pc]
            return Result((Value(self._peek()), ReturnKind.YIELD))

        f = getattr(self, '_run_{}'.format(instruction.opname))
        f_sets_pc = getattr(f, '_sets_pc', False)

        stack_depth_before = len(self.stack)
        result = f(arg=instruction.arg, argval=instruction.argval)
        log('bc:res', lambda: f'result {result}')
        if result is None or type(result) == bool:
            pass
        else:
            assert isinstance(result, Result), (
                'Bytecode must return Result', instruction, 'got', result)
            if result.is_exception():
                exception_data = result.get_exception()
                if not exception_data.traceback:
                    exception_data.traceback = etraceback.ETraceback(
                        EFrame(self), self.pc, self.line)
                if self._handle_exception(WhyStatus.EXCEPTION, exception_data,
                                          _Sentinel):
                    return None
                else:
                    return result
            elif isinstance(result.get_value(), Value):
                self._push_value(result.get_value())
            elif (not f_sets_pc and
                    result.get_value() is not NoStackPushSentinel):
                self._push(result.get_value())

        stack_depth_after = len(self.stack)
        if instruction.opname not in (
                # These opcodes claim a value-stack effect, but we use a
                # different stack for block info.
                'SETUP_EXCEPT', 'POP_EXCEPT', 'SETUP_FINALLY', 'END_FINALLY',
                'SETUP_WITH', 'WITH_CLEANUP_START', 'WITH_CLEANUP_FINISH',
                'CONTINUE_LOOP',
                # This op causes the stack_effect call to error.
                'EXTENDED_ARG', 'BREAK_LOOP',
                # These ops may or may not pop the stack.
                'JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP', 'FOR_ITER',
                ):
            stack_effect = dis.stack_effect(instruction.opcode,
                                            instruction.arg)
            assert stack_depth_after-stack_depth_before == stack_effect, (
                instruction, stack_depth_after, stack_depth_before,
                stack_effect)

        if ((not f_sets_pc) or
                (f_sets_pc and not self._maybe_box_result_truthy(result))):
            width = self.pc_to_bc_width[self.pc]
            self.pc += width

        return None

    def _maybe_box_result_truthy(
            self, result: Optional[Union[bool, Result[bool]]]) -> bool:
        if result is None:
            return False
        if isinstance(result, bool):
            return result
        assert isinstance(result, Result), result
        r = result.get_value()
        assert isinstance(r, bool)
        return r

    def run_to_return_or_yield(self) -> Result[Tuple[Value, ReturnKind]]:
        if (os.getenv('ECHO_DUMP_CODE')
                and os.getenv('ECHO_DUMP_CODE') in str(self.code)):
            print(self.code, file=sys.stderr)
            dis.dis(self.code)
        while True:
            bc_result = self._run_one_bytecode()
            if bc_result is None:
                continue
            return bc_result


class EFrameType(EPyType):
    def __repr__(self) -> Text:
        return f"<{E_PREFIX}class 'frame'>"

    def get_dict(self):
        raise NotImplementedError

    def get_bases(self):
        raise NotImplementedError

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return (self,)

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


EFrameType.singleton = EFrameType()


class EFrame(EPyObject):
    def __init__(self, frame: StatefulFrame):
        self.frame = frame

    @property
    def f_code(self):
        return self.frame.code

    @property
    def f_lineno(self):
        return self.frame.current_lineno

    @property
    def f_back(self) -> Optional['EFrame']:
        return (EFrame(self.frame.older_frame) if self.frame.older_frame
                else None)

    def __repr__(self) -> Text:
        return (f'<frame, file {self.frame.code.co_filename!r}, '
                f'line {self.frame.current_lineno}, '
                f'code {self.frame.code.co_name}>')

    def get_type(self) -> EPyType:
        return EFrameType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

import dis
import itertools
import functools
import operator
import os
import sys
import types
from typing import (
    List, Any, Text, Optional, Dict, Tuple, Callable, cast, Sequence
)
from enum import Enum

from echo.elog import log
from echo.interp_context import ICtx
from echo import import_routines
from echo.eobjects import (
    ReturnKind, EBuiltin, EFunction, EPyObject,
    GuestCoroutine, EInstance, get_guest_builtin,
    do_getitem, do_setitem, do_hasattr, do_getattr,
    do_iter, do_next, do_tuple, do_delitem,
)
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


# Use a sentinel value (this class object) to indicate when
# UnboundLocalErrors have occurred.
class UnboundLocalSentinel:
    pass


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
                 locals_dict: Dict[Text, Any],
                 globals_: Dict[Text, Any],
                 cellvars: Tuple[ECell, ...],
                 in_function: bool,
                 ictx: ICtx):
        self.code = code
        self.pc = 0
        self.stack = []
        self.block_stack = []  # type: List[BlockInfo]
        self.pc_to_instruction = pc_to_instruction
        self.pc_to_bc_width = pc_to_bc_width
        self.locals_ = locals_
        self.locals_dict = locals_dict
        self.globals_ = globals_
        self.exception_data = None  # type: Optional[ExceptionData]
        self.handling_exception_data = None  # type: Optional[ExceptionData]
        self.cellvars = cellvars
        self.consts = code.co_consts
        self.names = code.co_names
        self.ictx = ictx
        self.in_function = in_function

        # TODO(cdleary, 2019-01-21): Investigate why this "builtins" ref is
        # sometimes a dict and other times a module?
        self.builtins = sys.modules['builtins']  # globals_['__builtins__']

        self.interp_callback = wrap_with_push(
            self, ictx.interp_state, ictx.interp_callback)
        self.do_call_callback = wrap_with_push(
            self, ictx.interp_state, ictx.do_call_callback)

    @property
    def interp_state(self):
        return self.ictx.interp_state

    def _handle_exception(self):
        """Returns whether the exception was handled in this function."""
        # Pop until we see an except block, or there's no block stack left.
        while (self.block_stack and
               self.block_stack[-1].kind != BlockKind.SETUP_EXCEPT):
            self.block_stack.pop()

        if (self.block_stack and
                self.block_stack[-1].kind == BlockKind.SETUP_EXCEPT):
            # We wound up at an except block, pop back to the right value-stack
            # depth and start running the handler.
            self.pc = self.block_stack[-1].handler
            while len(self.stack) > self.block_stack[-1].level:
                self._pop()
            assert isinstance(self.exception_data, ExceptionData)
            self._push(self.exception_data.traceback)
            self._push(self.exception_data.exception)
            self._push(self.exception_data.exception)
            # The block stack entry transmorgifies into an EXCEPT_HANDLER.
            self.block_stack[-1].kind = BlockKind.EXCEPT_HANDLER
            self.block_stack[-1].handler = -1
            self.handling_exception_data, self.exception_data = (
                self.exception_data, None)
            return True
        elif not any(entry.kind == BlockKind.SETUP_EXCEPT
                     for entry in self.block_stack):
            return False  # Definitely unhandled.
        else:
            # Need to pop block stack entries appropriately, then handle the
            # exception.
            raise NotImplementedError(self.block_stack)

    def _push(self, x: Any) -> None:
        assert not isinstance(x, Result), x
        # If the user can observe the real isinstance they can break the
        # virtualization abstraction, which is undesirable.
        assert x is not isinstance
        assert x is not tuple
        assert x is not dict
        assert not isinstance(x, Value), x
        assert x is not GuestCoroutine
        log('fo:push()', repr(x))
        self.stack.append(x)

    def _push_value(self, x: Value) -> None:
        self._push(x.wrapped)

    def _pop(self) -> Any:
        x = self.stack.pop()
        return x

    def _pop_value(self) -> Value:
        return Value(self._pop())

    def _pop_n(self, n: int, tos_is_0: bool = True) -> Tuple[Any, ...]:
        self.stack, result = (
            self.stack[:len(self.stack)-n], self.stack[len(self.stack)-n:])
        if tos_is_0:
            return tuple(reversed(result))
        return tuple(result)

    def _peek(self):
        return self.stack[-1]

    def _peek_value(self) -> Value:
        return Value(self._peek())

    def _get_global_or_builtin(self, name: Text) -> Any:
        try:
            return self.globals_[name]
        except KeyError:
            pass
        return interp_routines.builtins_get(self.builtins, name)

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
        if isinstance(tos1, (dict, list)):
            del tos1[tos]
        elif isinstance(tos1, EPyObject):
            r = do_delitem((tos1, tos), self.ictx)
            assert not r.is_exception(), r
        else:
            raise NotImplementedError(tos, tos1)

    def _run_LOAD_CONST(self, arg, argval):
        return Result(self.consts[arg])

    def _run_GET_ITER(self, arg, argval):
        return do_iter((self._pop(),), self.ictx)

    def _run_LOAD_BUILD_CLASS(self, arg, argval):
        return Result(get_guest_builtin('__build_class__'))

    def _run_BUILD_TUPLE(self, arg, argval):
        count = arg
        t = self._pop_n(count, tos_is_0=False)
        return Result(t)

    def _run_BUILD_TUPLE_UNPACK(self, arg, argval):
        iterables = self._pop_n(arg, tos_is_0=False)
        return Result(tuple(itertools.chain(*iterables)))

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
        popped = self.block_stack.pop()
        assert popped.kind in (BlockKind.SETUP_EXCEPT,
                               BlockKind.EXCEPT_HANDLER), (
            'Popped non-except block.', popped)

    def _run_SETUP_FINALLY(self, arg, argval):
        # "Pushes a try block from a try-except clause onto the block stack.
        # delta points to the finally block."
        # -- https://docs.python.org/3.7/library/dis.html#opcode-SETUP_FINALLY
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_FINALLY, arg+self.pc+self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_DELETE_NAME(self, arg, argval):
        if self.in_function:
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

    @sets_pc
    def _run_BREAK_LOOP(self, arg, argval):
        loop_block = self.block_stack[-1]
        assert loop_block.kind == BlockKind.SETUP_LOOP
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

    @sets_pc
    def _run_POP_JUMP_IF_FALSE(self, arg, argval):
        v = self._pop_value()
        if v.is_falsy():
            log('bc:pjif', f'jumping on falsy: {v}')
            self.pc = arg
            return True
        log('bc:pjif', f'not jumping, truthy: {v}')
        return False

    @sets_pc
    def _run_POP_JUMP_IF_TRUE(self, arg, argval):
        v = self._pop_value()
        if v.is_truthy():
            log('bc:pjit', f'jumping on truthy: {v}')
            self.pc = arg
            return True
        log('bc:pjit', f'not jumping, falsy: {v}')
        return False

    @sets_pc
    def _run_JUMP_IF_FALSE_OR_POP(self, arg, argval):
        if self._peek_value().is_falsy():
            self.pc = arg
            return True
        else:
            self._pop()
            return False

    @sets_pc
    def _run_JUMP_IF_TRUE_OR_POP(self, arg, argval):
        if self._peek_value().is_truthy():
            self.pc = arg
            return True
        else:
            self._pop()
            return False

    @sets_pc
    def _run_FOR_ITER(self, arg, argval):
        o = self._peek()
        r = do_next((o,), self.ictx)
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
        log('fo:cf', f'f: {f} args: {args}')
        result = self.do_call_callback(
            f, args, kwargs, locals_dict=self.locals_dict,
            globals_=self.globals_, get_exception_data=self.get_exception_data)
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

    def _run_STORE_ATTR(self, arg, argval):
        obj = self._pop()
        value = self._pop()
        log('bc:sa', f'obj {obj!r} attr {argval!r} val {value!r}')
        if isinstance(obj, EPyObject):
            res = obj.setattr(argval, value, ictx=self.ictx)
            if res.is_exception():
                return res
            return Result(NoStackPushSentinel)
        elif obj is sys and argval == 'path':
            sys.path = self.interp_state.paths = value
            return Result(NoStackPushSentinel)
        else:
            raise NotImplementedError(obj, value)

    def _run_STORE_GLOBAL(self, arg, argval):
        self.globals_[argval] = self._pop()

    def _run_MAKE_CLOSURE(self, arg, argval):
        # Note: this bytecode was removed in Python 3.6.
        name = self._pop()
        code = self._pop()
        freevar_cells = self._pop()
        defaults = self._pop_n(arg)
        f = EFunction(code, self.globals_, name, defaults=defaults,
                      closure=freevar_cells)
        return Result(f)

    def _run_LOAD_FAST(self, arg, argval):
        v = self.locals_[arg]
        if v is UnboundLocalSentinel:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(None, None, NameError(msg)))
        return Result(v)

    def _run_IMPORT_NAME(self, arg, argval):
        fromlist = self._pop()
        level = self._pop()
        return import_routines.run_IMPORT_NAME(
            self.code.co_filename, level, fromlist, argval, self.globals_,
            self.ictx)

    def _run_IMPORT_FROM(self, arg, argval):
        module = self._peek()
        if isinstance(module, types.ModuleType):
            return Result(getattr(module, argval))
        elif isinstance(module, EModule):
            return import_routines.getattr_or_subimport(
                module, argval, self.ictx)
        else:
            raise NotImplementedError(module)

    def _run_LOAD_GLOBAL(self, arg, argval):
        namei = arg
        name = self.names[namei]
        return Result(self._get_global_or_builtin(name))

    def _run_LOAD_NAME(self, arg, argval):
        if self.in_function:
            if self.locals_dict is not None:
                try:
                    return do_getitem((self.locals_dict, argval), self.ictx)
                except KeyError:
                    pass
            else:
                return Result(self.locals_[arg])
        try:
            return Result(self._get_global_or_builtin(argval))
        except AttributeError:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(
                None, None, NameError(msg)))

    def _run_LOAD_ATTR(self, arg, argval) -> Result[Any]:
        obj = self._pop()
        log('bc:la', f'obj {obj!r} attr {argval}')
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
        log('bc:la', f'obj {obj!r} attr {argval} => {r}')
        return r

    def _run_COMPARE_OP(self, arg, argval):
        rhs = self._pop()
        lhs = self._pop()
        if argval == 'exception match':
            return interp_routines.exception_match(lhs, rhs, self.ictx)
        else:
            return interp_routines.compare(
                argval, lhs, rhs, self.ictx)

    def _run_END_FINALLY(self, arg, argval):
        # From the Python docs: "The interpreter recalls whether the
        # exception has to be re-raised, or whether the function returns,
        # and continues with the outer-next block."
        if self.exception_data is None:
            pass
        else:
            raise NotImplementedError(self.handling_exception_data,
                                      self.exception_data)

    def _run_UNARY_NOT(self, arg, argval) -> None:
        arg = self._pop_value()
        self._push(arg.is_falsy())

    def _run_binary(self, opname):
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

    def _run_INPLACE_ADD(self, arg, argval):
        rhs = self._pop()
        lhs = self._pop()
        if ({type(lhs), type(rhs)} <=
                interp_routines.BUILTIN_VALUE_TYPES | {list}):
            return interp_routines.run_binop(
                'BINARY_ADD', lhs, rhs, self.ictx)
        else:
            raise NotImplementedError(lhs, rhs)

    def _run_SETUP_EXCEPT(self, arg, argval):
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_EXCEPT, arg+self.pc+self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_STORE_SUBSCR(self, arg, argval) -> None:
        tos = self._pop()
        tos1 = self._pop()
        tos2 = self._pop()
        log('bc:store_subscr', f'd: {tos1} k: {tos} v: {tos2}')
        r = do_setitem((tos1, tos, tos2), self.ictx)
        assert not r.is_exception(), r

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
            globals_=self.globals_, get_exception_data=self.get_exception_data)

    def _run_SETUP_LOOP(self, arg, argval):
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_LOOP, arg + self.pc + self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_RAISE_VARARGS(self, arg, argval):
        argc = arg
        traceback, parameter, exception = (None, None, None)
        if argc > 2:
            traceback = self._pop()
        if argc > 1:
            parameter = self._pop()
        if argc > 0:
            exception = self._pop()
        if (isinstance(exception, type)
                and issubclass(exception, BaseException)):
            exception = exception()
        return Result(ExceptionData(traceback, parameter, exception))

    def get_exception_data(self) -> Optional[ExceptionData]:
        return self.handling_exception_data

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
        self._push(attr_result.get_value())
        if (desc_count_before == self.ictx.desc_count
                and interp_routines.method_requires_self(
                    obj=obj, name=argval, value=attr_result.get_value())):
            self._push(obj)
        else:
            self._push(UnboundLocalSentinel)

    def _run_CALL_METHOD(self, arg, argval):
        # Note: new in 3.7. See also _run_LOAD_METHOD
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-CALL_METHOD
        positional_argc = arg
        args = self._pop_n(positional_argc, tos_is_0=False)
        self_value = self._pop()
        method = self._pop()
        if self_value is not UnboundLocalSentinel:
            args = (self_value,) + args
        log('bc:cm', f'method: {method}')
        log('bc:cm', f'args: {args}')
        log('bc:cm', f'self_value: {self_value}')
        return self.do_call_callback(
            method, args, {}, self.locals_dict,
            globals_=self.globals_,
            get_exception_data=self.get_exception_data)

    def _run_CALL_FUNCTION_EX(self, arg, argval):
        if arg & 0x1:
            kwargs = self._pop()
        else:
            kwargs = None
        callargs = self._pop()
        if not isinstance(callargs, tuple):
            callargs = do_tuple((callargs,), {}, self.ictx)
            if callargs.is_exception():
                return callargs
            callargs = callargs.get_value()
        func = self._pop()
        return self.do_call_callback(
            func, callargs, kwargs, self.locals_dict, globals_=self.globals_,
            get_exception_data=self.get_exception_data)

    def _run_PRINT_EXPR(self, arg, argval):
        value = self._pop()
        if value is not None:
            if isinstance(value, EPyObject):
                r = value.getattr('__repr__', self.ictx)
                s = self.do_call_callback(
                    r, (), {}, self.locals_dict, globals_=r.globals_,
                    get_exception_data=self.get_exception_data)
                print(s)
            else:
                print(repr(value))

    def _run_IMPORT_STAR(self, arg, argval):
        module = self._peek()
        import_routines.import_star(module, self.globals_, self.ictx)
        self._pop()  # Docs say 'module is popped after loading all names'.

    def _run_UNPACK_EX(self, arg, argval):
        tos = self._pop()
        it = do_iter((tos,), self.ictx)
        if it.is_exception():
            return it
        it = it.get_value()
        stack_values = []
        for _ in range(arg):
            r = do_next((it,), self.ictx)
            if r.is_exception():
                return r
            stack_values.append(r.get_value())
        rest = []
        while True:
            r = do_next((it,), self.ictx)
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

    def _run_UNPACK_SEQUENCE(self, arg, argval):
        # https://docs.python.org/3.7/library/dis.html#opcode-UNPACK_SEQUENCE
        t = self._pop()  # type: Sequence
        # Want to make sure we have a test that exercises this behavior
        # properly, I expect it leaves the remainder in a tuple when arg is <
        # len.
        assert len(t) == arg
        for e in t[::-1]:
            self._push(e)

    def _run_EXTENDED_ARG(self, arg, argval):
        pass  # The to-instruction decoding step already extended the args?

    def _run_one_bytecode(self) -> Optional[Result[Tuple[Value, ReturnKind]]]:
        instruction = self.pc_to_instruction[self.pc]
        assert instruction is not None

        if instruction.starts_line:
            log('bc:line',
                f'{self.code.co_filename}:{instruction.starts_line}')

        log('bc:inst', instruction)

        if instruction.starts_line is not None:
            self.line = instruction.starts_line

        if instruction.opname == 'RETURN_VALUE':
            v = self._pop_value()
            log('bc:rv', repr(v))
            return Result((v, ReturnKind.RETURN))

        if instruction.opname == 'YIELD_VALUE':
            self.pc += self.pc_to_bc_width[self.pc]
            return Result((self._peek_value(), ReturnKind.YIELD))

        f = getattr(self, '_run_{}'.format(instruction.opname))

        stack_depth_before = len(self.stack)
        result = f(arg=instruction.arg, argval=instruction.argval)
        log('bc:res', f'result {result}')
        if result is None or type(result) == bool:
            pass
        else:
            assert isinstance(result, Result), (
                'Bytecode must return Result', instruction, 'got', result)
            if result.is_exception():
                self.exception_data = result.get_exception()
                self.exception_data.traceback.append(
                    (self.code.co_filename, self.line))
                if self._handle_exception():
                    return None
                else:
                    return result
            elif isinstance(result.get_value(), Value):
                self._push_value(result.get_value())
            elif result.get_value() is not NoStackPushSentinel:
                self._push(result.get_value())

        stack_depth_after = len(self.stack)
        if instruction.opname not in (
                # These opcodes claim a value-stack effect, but we use a
                # different stack for block info.
                'SETUP_EXCEPT', 'POP_EXCEPT', 'SETUP_FINALLY', 'END_FINALLY',
                # This op causes the stack_effect call to error.
                'EXTENDED_ARG',
                # These ops may or may not pop the stack.
                'JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP', 'FOR_ITER',
                ):
            stack_effect = dis.stack_effect(instruction.opcode,
                                            instruction.arg)
            assert stack_depth_after-stack_depth_before == stack_effect, (
                instruction, stack_depth_after, stack_depth_before,
                stack_effect)

        f_sets_pc = getattr(f, '_sets_pc', False)
        if (not f_sets_pc) or (f_sets_pc and not result):
            width = self.pc_to_bc_width[self.pc]
            self.pc += width

        return None

    def run_to_return_or_yield(self) -> Result[Tuple[Value, ReturnKind]]:
        while True:
            bc_result = self._run_one_bytecode()
            if bc_result is None:
                continue
            return bc_result

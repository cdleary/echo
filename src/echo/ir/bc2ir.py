from typing import Tuple, Any, Text, List, Optional

import dis
import enum
import sys
import types

from echo.elog import log
from echo import bc_helpers
from echo.ir import ir


class UnhandledConversionError(Exception):
    pass


def bytecode_to_ir(code: types.CodeType) -> ir.Cfg:
    cfg = ir.Cfg()
    bb = cfg.add_block('bc0')
    inst_to_node = {}
    virtual_stack = []  # type: List[ir.Node]
    locals_ = [None] * code.co_nlocals  # type: List[Optional[ir.Node]]
    insts = list(dis.get_instructions(code))
    dis.dis(code)
    print(dir(code))
    print('argcount:', code.co_argcount)
    print('names:   ', code.co_names)
    print('varnames:', code.co_varnames)
    print('freevars:', code.co_freevars)

    for i in range(code.co_argcount):
        locals_[i] = ir.Param(code.co_varnames[i])

    def fpop_n(n: int) -> Tuple[ir.Node, ...]:
        return tuple(virtual_stack.pop() for _ in range(n))

    for instno, inst in enumerate(insts):
        if inst.opname in ('SETUP_LOOP', 'POP_BLOCK'):
            continue  # For now we ignore the block stack.

        try:
            width = insts[instno+1].offset-inst.offset
        except IndexError:
            width = 0

        def bb_add_and_stack_push(node: ir.Node) -> ir.Node:
            assert isinstance(node, ir.Node), node
            inst_to_node[inst] = node
            bb.add_node(node)
            virtual_stack.append(node)
            return node

        pc = inst.offset

        if inst.is_jump_target:
            new_label = f'bc{pc}'
            if not bb.control:
                bb.control = ir.JumpAbs(new_label)
            bb = cfg.add_block(new_label)

        if inst.opname == 'LOAD_CONST':
            if isinstance(inst.argval, types.CodeType):
                cfg_num = len(cfg.dependent)
                cfg.dependent[inst.argval] = bytecode_to_ir(inst.argval)
                bb_add_and_stack_push(ir.LoadCfg(pc, cfg_num))
            else:
                bb_add_and_stack_push(ir.LoadConst(pc, inst.argval))
        elif inst.opname == 'LOAD_GLOBAL':
            bb_add_and_stack_push(ir.LoadGlobal(pc, inst.argval))
        elif inst.opname == 'CALL_FUNCTION':
            f, args, kwargs = bc_helpers.do_CALL_FUNCTION(fpop_n, inst.arg,
                                                          sys.version_info)
            bb_add_and_stack_push(ir.CallFn(pc, f, args, kwargs))
        elif inst.opname == 'LOAD_FAST':
            node = locals_[inst.arg]
            assert isinstance(node, ir.Node), node
            virtual_stack.append(node)
        elif inst.opname == 'LOAD_NAME':
            bb_add_and_stack_push(ir.LoadName(pc, inst.argval))
        elif inst.opname == 'LOAD_ATTR':
            obj = virtual_stack.pop()
            bb_add_and_stack_push(ir.LoadAttr(pc, obj, inst.argval))
        elif inst.opname == 'STORE_NAME':
            value = virtual_stack.pop()
            bb.add_node(ir.StoreName(pc, inst.argval, value))
        elif inst.opname == 'STORE_FAST':
            node = virtual_stack.pop()
            assert isinstance(node, ir.Node), node
            locals_[inst.arg] = node
        elif inst.opname == 'STORE_ATTR':
            obj = virtual_stack.pop()
            value = virtual_stack.pop()
            bb_add_and_stack_push(ir.StoreAttr(pc, obj, inst.argval, value))
        elif inst.opname in ('BINARY_ADD', 'BINARY_MULTIPLY'):
            rhs = virtual_stack.pop()
            lhs = virtual_stack.pop()
            make_ir = {
                'BINARY_ADD': ir.Add,
                'BINARY_MULTIPLY': ir.Mul,
            }[inst.opname]
            bb_add_and_stack_push(make_ir(pc, lhs, rhs))
        elif inst.opname == 'LIST_APPEND':
            to_append = virtual_stack.pop()
            log('bc2ir', f'LIST_APPEND to_append: {to_append}')
            lst = virtual_stack[-inst.arg]
            bb_add_and_stack_push(ir.ListAppend(pc, lst, to_append))
        elif inst.opname == 'COMPARE_OP':
            rhs = virtual_stack.pop()
            lhs = virtual_stack.pop()
            log('bc2ir', f'COMPARE_OP lhs: {lhs} rhs: {rhs}')
            bb_add_and_stack_push(ir.Cmp(pc, inst.argval, lhs, rhs))
        elif inst.opname == 'BUILD_LIST':
            count = inst.arg
            limit = len(virtual_stack)-count
            virtual_stack, t = virtual_stack[:limit], virtual_stack[limit:]
            bb_add_and_stack_push(ir.BuildList(pc, tuple(t)))
        elif inst.opname == 'GET_ITER':
            arg = virtual_stack.pop()
            bb_add_and_stack_push(ir.GetIter(pc, arg))
        elif inst.opname == 'FOR_ITER':
            it = virtual_stack[-1]
            log('bc2ir', f'FOR_ITER TOS: {it}')
            node = bb_add_and_stack_push(ir.Next(pc, it))
            bb.add_control(ir.JumpOnStopIteration(
                node, 'bc{}'.format(inst.offset + inst.arg + width)))
            bb = cfg.add_block(f'bc{inst.offset+width}')
        elif inst.opname == 'POP_JUMP_IF_FALSE':
            arg = virtual_stack.pop()
            bb.add_control(ir.JumpOnFalse(arg, f'bc{inst.arg}'))
            bb = cfg.add_block(f'bc{inst.offset+width}')
        elif inst.opname == 'JUMP_ABSOLUTE':
            bb.add_control(ir.JumpAbs(f'bc{inst.arg}'))
            bb = cfg.add_block(f'bc{inst.offset+width}')
        elif inst.opname == 'MAKE_FUNCTION':
            mfd = bc_helpers.do_MAKE_FUNCTION(
                virtual_stack.pop, inst.arg, sys.version_info)
            bb_add_and_stack_push(ir.MakeFunction(
                pc, mfd.qualified_name, mfd.code, mfd.positional_defaults,
                mfd.kwarg_defaults, mfd.freevar_cells))
        elif inst.opname == 'RETURN_VALUE':
            retval = virtual_stack.pop()
            bb.add_control(ir.Return(retval))
        elif inst.opname in ('IMPORT_NAME', 'YIELD_VALUE'):
            raise UnhandledConversionError
        else:
            raise NotImplementedError(inst)

    return cfg

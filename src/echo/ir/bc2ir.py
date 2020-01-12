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
    virtual_stack = []
    locals_ = [None] * code.co_nlocals  # type: List[Optional[ir.Node]]
    insts = list(dis.get_instructions(code))
    dis.dis(code)
    print('names:   ', code.co_names)
    print('varnames:', code.co_varnames)
    print('freevars:', code.co_freevars)

    def fpop_n(n: int) -> Tuple[Any, ...]:
        return tuple(virtual_stack.pop() for _ in range(n))

    for instno, inst in enumerate(insts):
        if inst.opname in ('SETUP_LOOP', 'POP_BLOCK'):
            continue  # For now we ignore the block stack.

        try:
            width = insts[instno+1].offset-inst.offset
        except IndexError:
            width = 0

        def bb_add_and_stack_push(node: ir.Node) -> ir.Node:
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
            bb_add_and_stack_push(ir.LoadConst(pc, inst.argval))
        elif inst.opname == 'LOAD_GLOBAL':
            bb_add_and_stack_push(ir.LoadGlobal(pc, inst.argval))
        elif inst.opname == 'CALL_FUNCTION':
            f, args, kwargs = bc_helpers.do_CALL_FUNCTION(fpop_n, inst.arg,
                                                          sys.version_info)
            bb_add_and_stack_push(ir.CallFn(pc, f, args, kwargs))
        elif inst.opname == 'LOAD_FAST':
            node = locals_[inst.arg]
            virtual_stack.append(node)
        elif inst.opname == 'LOAD_NAME':
            bb_add_and_stack_push(ir.LoadName(pc, inst.argval))
        elif inst.opname == 'STORE_NAME':
            value = virtual_stack.pop()
            bb.add_node(ir.StoreName(pc, inst.argval, value))
        elif inst.opname == 'STORE_FAST':
            node = virtual_stack.pop()
            locals_[inst.arg] = node
        elif inst.opname == 'BINARY_ADD':
            rhs = virtual_stack.pop()
            lhs = virtual_stack.pop()
            bb_add_and_stack_push(ir.Add(pc, lhs, rhs))
        elif inst.opname == 'BUILD_LIST':
            count = inst.arg
            limit = len(virtual_stack)-count
            virtual_stack, t = virtual_stack[:limit], virtual_stack[limit:]
            bb_add_and_stack_push(ir.BuildList(pc, tuple(t)))
        elif inst.opname == 'GET_ITER':
            arg = virtual_stack.pop()
            bb_add_and_stack_push(ir.GetIter(pc, arg))
        elif inst.opname == 'FOR_ITER':
            it = virtual_stack.pop()
            log('bc2ir', f'FOR_ITER TOS: {it}')
            node = bb_add_and_stack_push(ir.Next(pc, it))
            bb.add_control(ir.JumpOnStopIteration(
                node, 'bc{}'.format(inst.offset + inst.arg + width)))
            bb = cfg.add_block(f'bc{inst.offset+width}')
        elif inst.opname == 'JUMP_ABSOLUTE':
            bb.add_control(ir.JumpAbs(f'bc{inst.arg}'))
            bb = cfg.add_block(f'bc{inst.offset+width}')
        elif inst.opname == 'MAKE_FUNCTION':
            raise UnhandledConversionError
        elif inst.opname == 'RETURN_VALUE':
            retval = virtual_stack.pop()
            bb.add_control(ir.Return(retval))
        else:
            raise NotImplementedError(inst)

    return cfg

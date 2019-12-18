import ctypes
import sys
import types
from typing import Any

from echo import trace_util


# pytype: disable=base-class-error
class _PyTryBlock(ctypes.Structure):
    _fields_ = [
        ('b_type', ctypes.c_uint),
        ('b_handler', ctypes.c_uint),
        ('b_level', ctypes.c_uint),
    ]
# pytype: enable=base-class-error


class CtypeFrame:
    """Wraps interpreter frame to allow inspection of interpreter-private data.

    Stack inspection inspired by the approach shown in:

        http://code.activestate.com/recipes/578412-peek-at-python-value-stack/
    """

    VERSION_TO_CTYPE_ULONG_OFFSETS = {
        (3, 7): {
            'f_back': 3,
            'f_code': 4,
            'f_builtins': 5,
            'f_globals': 6,
            'f_locals': 7,  # "Local symbol table".
            'f_valuestack': 8,
            'f_stacktop': 9,
            'f_localsplus': 45,
        },
    }
    ULONG_SIZE_IN_BYTES = 8
    UINT_SIZE_IN_BYTES = 4
    PTR_TO_LONG = ctypes.POINTER(ctypes.c_ulong)

    def __init__(self, frame: types.FrameType):
        self.frame_id = id(frame)
        self.frame_ptr = ctypes.cast(id(frame),
                                     self.PTR_TO_LONG)
        self.offsets = self.VERSION_TO_CTYPE_ULONG_OFFSETS[
            sys.version_info[:2]]
        for offset in range(30):
            if id(frame.f_back) == self.frame_ptr[offset]:
                self.f_back_offset = offset

    @classmethod
    def _id2obj(cls, id_: int) -> Any:
        """Mutates a tuple cell to point at a new location."""
        t = (None,)
        try:
            ctypes.cast(id(t), cls.PTR_TO_LONG)[3] = id_
            return t[0]
        finally:
            # Do we need to do this to keep the refcounts sane?
            ctypes.cast(id(t), cls.PTR_TO_LONG)[3] = id(None)

    def get_value_stack(self):
        """Returns the contents of the f_valuestack slot in the PyFrameObject.

        In C the type of the returned value is ``PyObject**``.
        """
        return self.frame_ptr[self.offsets['f_valuestack']]

    def get_value_stack_as_ptr(self):
        return ctypes.cast(self.get_value_stack(),
                           self.PTR_TO_LONG)

    def get_localsplus_start(self):
        """Returns a pointer to the "localsplus" region of the PyFrameObject.

        This is the start of a variable sized region.

        In C the type of the returned value is ``PyObject**``.
        """
        return (self.frame_id +
                self.offsets['f_localsplus'] * self.ULONG_SIZE_IN_BYTES)

    def get_localsplus_start_as_ptr(self):
        return ctypes.cast(self.get_localsplus_start(),
                           self.PTR_TO_LONG)

    def get_stack_top(self):
        """Returns a pointer to the next free slot in the value stack.

        In C the type of the returned value is ``PyObject**``.
        """
        return self.frame_ptr[self.offsets['f_stacktop']]

    def print_block_stack(self, printer):
        assert sys.version_info[:2] == (3, 7)
        f_iblock = ctypes.cast(
            self.frame_id,
            ctypes.POINTER(ctypes.c_uint))[112//self.UINT_SIZE_IN_BYTES]
        printer('f_iblock:', f_iblock)

        type_to_str = {
            257: 'EXCEPT_HANDLER',
            120: 'SETUP_LOOP',
            121: 'SETUP_EXCEPT',
            122: 'SETUP_FINALLY',
        }

        f_blockstack = ctypes.cast(self.frame_id+120,
                                   ctypes.POINTER(_PyTryBlock))
        block_stack = []
        for i in range(f_iblock):
            ptb = f_blockstack[i]
            type_str = type_to_str[ptb.b_type]
            handler = -1 if ptb.b_handler == 0xffffffff else ptb.b_handler
            printer(' blockstack %d: type: %s handler: %s level: %d' % (
                    i, type_str, handler, ptb.b_level))

    def get_tos_value(self, i=0):
        value = self.get_value_stack_as_ptr()[i]
        if value == 0:
            return None
        return self._id2obj(value)

    def print_stack(self, *, do_localsplus: bool, printer=print):
        # Left in, just in case there's some need to look at the pointer
        # values.
        #
        # print(' frame start   (frameobj*):', hex(self.frame_id))
        # print(' localplus start (pyobj**):',
        #       hex(self.get_localsplus_start()))
        # print(' value stack     (pyobj**):', hex(self.get_value_stack()))
        # print(' stack top       (pyobj**):', hex(self.get_stack_top()))

        count = self.get_stack_top() - self.get_value_stack()
        assert count % self.ULONG_SIZE_IN_BYTES == 0
        stack_items = count // self.ULONG_SIZE_IN_BYTES

        if do_localsplus:
            localsplus_items = (
                (self.get_stack_top() - self.get_localsplus_start()) //
                self.ULONG_SIZE_IN_BYTES)
            printer(' localsplus_items sans stack:',
                    localsplus_items-stack_items)
            for i in range(localsplus_items-stack_items):
                localsplus_ptr = self.get_localsplus_start_as_ptr()
                value = localsplus_ptr[i]
                if value == 0:
                    printer('  LP{}: <null>'.format(i))
                else:
                    obj = self._id2obj(value)
                    printer('  LP{}: {!r} :: {!r}'.format(i, type(obj), obj))

        printer(' stack (%d):' % stack_items)
        for i in range(stack_items):
            stack_value = self.get_value_stack_as_ptr()[stack_items-i-1]
            if stack_value == 0:
                printer('  TOS%d: <null>' % i)
            else:
                obj = self._id2obj(stack_value)
                try:
                    r = repr(obj)
                except Exception:
                    r = '<unreprable>'
                printer('  TOS%d: %r ::' % (i, type(obj)),
                        trace_util.remove_at_hex(r))  # , '::', id(obj))
                if isinstance(obj, types.CodeType):
                    printer('    co_varnames: {!r}'.format(obj.co_varnames))
                    printer('    co_cellvars: {!r}'.format(obj.co_cellvars))
                if isinstance(obj, types.FunctionType):
                    printer('    closure:     {!r}'.format(obj.__closure__))
                    printer('    co_cellvars: {!r}'.format(
                            obj.__code__.co_cellvars))
                    printer('    co_freevars: {!r}'.format(
                            obj.__code__.co_freevars))
        self.print_block_stack(printer)

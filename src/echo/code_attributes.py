from typing import Optional, Tuple, Text
import types


class CodeAttributes:
    STARARGS_FLAG = 0x04
    STARKWARGS_FLAG = 0x08
    GENERATOR_FLAG = 0x20
    COROUTINE_FLAG = 0x80
    ASYNC_GENERATOR_FLAG = 0x200

    def __init__(self, argcount: int, kwonlyargcount: int, nlocals: int,
                 starargs: bool, starkwargs: bool, coroutine: bool,
                 varnames: Tuple[Text, ...], cellvars: Tuple[Text, ...],
                 freevars: Tuple[Text, ...],
                 generator: bool, async_generator: bool, name: Text, *,
                 code: Optional[types.CodeType] = None):
        assert len(varnames) == nlocals
        self.argcount = argcount
        self.kwonlyargcount = kwonlyargcount
        self.nlocals = nlocals
        self.varnames = varnames
        self.cellvars = cellvars
        self.freevars = freevars
        self.starargs = starargs
        self.starkwargs = starkwargs
        self.coroutine = coroutine
        self.generator = generator
        self.async_generator = async_generator
        self.code = code
        self.name = name

    @property
    def stararg_index(self) -> int:
        return self.argcount + self.kwonlyargcount

    @property
    def starkwarg_index(self) -> int:
        return self.argcount + self.kwonlyargcount + self.starargs

    @property
    def total_argcount_no_skwa(self) -> int:
        """Returns the total number of argument slots, sans **kwargs.

        In functions like:

            def f(x, *, y=3, z=4): ...

        argcount=1 and kwargcount=2, but there are three local slots
        attributable to args. This attribute is `3` for that function.
        """
        return self.argcount + self.kwonlyargcount + self.starargs

    @property
    def total_argcount(self) -> int:
        return self.total_argcount_no_skwa + self.starkwargs

    def __repr__(self) -> Text:
        return ('CodeAttributes(argcount={0.argcount}, '
                'kwonlyargcount={0.kwonlyargcount}, '
                'nlocals={0.nlocals}, varnames={0.varnames}, '
                'starargs={0.starargs})').format(self)

    @classmethod
    def from_code(cls, code: types.CodeType, name: Text) -> 'CodeAttributes':
        """Creates CodeAttributes with values extracted from VM code object."""
        return cls(
            argcount=code.co_argcount,
            kwonlyargcount=code.co_kwonlyargcount,
            nlocals=code.co_nlocals,
            varnames=code.co_varnames,
            cellvars=code.co_cellvars,
            freevars=code.co_freevars,
            starargs=bool(code.co_flags & cls.STARARGS_FLAG),
            starkwargs=bool(code.co_flags & cls.STARKWARGS_FLAG),
            generator=bool(code.co_flags & cls.GENERATOR_FLAG),
            async_generator=bool(code.co_flags & cls.ASYNC_GENERATOR_FLAG),
            coroutine=bool(code.co_flags & cls.COROUTINE_FLAG),
            code=code, name=name)

import dataclasses
from typing import (
    Callable, Tuple, Text, Optional, Any, List,
)

VersionInfo = Tuple[int, int, int, str, int]


def do_CALL_FUNCTION(fpop_n: Callable[[int], Tuple[Any, ...]], arg: int,
                     version_info: VersionInfo):
    # https://docs.python.org/3.7/library/dis.html#opcode-CALL_FUNCTION
    #
    # Note: As of Python 3.6 this only supports calls for functions with
    # positional arguments.
    if version_info >= (3, 6):
        argc = arg
        kwargc = 0
    else:
        argc = arg & 0xff
        kwargc = arg >> 8
    kwarg_stack = fpop_n(2 * kwargc)
    kwargs = dict(zip(kwarg_stack[::2], kwarg_stack[1::2]))
    args = fpop_n(argc)
    f = fpop_n(1)[0]
    return (f, args, kwargs)


Node = Any


@dataclasses.dataclass
class MakeFunctionData:
    qualified_name: Node
    code: Node
    positional_defaults: Optional[Tuple[Node, ...]]
    kwarg_defaults: Optional[Tuple[Tuple[Text, Node], ...]]
    freevar_cells: Optional[Any]


def _make_fpop_n(fpop: Callable[[], Node]) -> Callable[[int], List[Node]]:
    def fpop_n(count: int) -> List[Node]:
        """Pops count items and puts TOS at the end."""
        return list(reversed([fpop() for _ in range(count)]))

    return fpop_n


def do_MAKE_FUNCTION(fpop: Callable[[], Node], arg: int,
                     version_info: VersionInfo) -> MakeFunctionData:
    if version_info >= (3, 6):
        qualified_name = fpop()
        code = fpop()
        freevar_cells = fpop() if arg & 0x08 else None
        annotation_dict = fpop() if arg & 0x04 else None
        kwarg_defaults = fpop() if arg & 0x02 else None
        positional_defaults = fpop() if arg & 0x01 else None
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
        qualified_name = fpop()
        code = fpop()
        fpop_n = _make_fpop_n(fpop)
        kwarg_default_items = fpop_n(2 * name_and_default_pairs)
        kwarg_defaults = tuple(zip(kwarg_default_items[::2],
                                   kwarg_default_items[1::2]))
        positional_defaults = fpop_n(default_argc)
        freevar_cells = None

    return MakeFunctionData(qualified_name, code, positional_defaults,
                            kwarg_defaults, freevar_cells)

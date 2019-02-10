import builtins
import logging
import os
import sys
import types
from typing import Text, Dict, Any, Optional, Union, Sequence, List

from interp_result import Result, ExceptionData
from interpreter_state import InterpreterState
from guest_objects import GuestModule

from termcolor import cprint


COLOR_TRACE = False


ModuleT = Union[types.ModuleType, GuestModule]


def _find_module_path(search_path: Text,
                      pieces: Sequence[Text]) -> Optional[Text]:
    *leaders, last = pieces
    candidate = os.path.join(search_path, *leaders)
    logging.debug('Candidate: %r', candidate)
    if os.path.exists(candidate):
        if os.path.isdir(os.path.join(candidate, last)):
            init_path = os.path.join(candidate, last, '__init__.py')
            if os.path.exists(init_path):
                return init_path
        target = os.path.join(candidate, last + '.py')
        if os.path.exists(target):
            return target
    return None


def find_module_path(name: Text,
                     paths: Sequence[Text]) -> Optional[Text]:
    pieces = name.split('.')

    for search_path in paths:
        result = _find_module_path(search_path, pieces)
        if result:
            return result
    return None


def import_path(path: Text, fully_qualified: Text,
                interp,
                state: InterpreterState) -> Result[GuestModule]:
    logging.debug('Importing path: %r', path)
    fullpath = path
    path, basename = os.path.split(fullpath)
    module_name, _ = os.path.splitext(basename)
    # Note: if we import the module it'll execute via the host interpreter.
    #
    # Instead, we need to go through the steps ourselves (read file, parse to
    # AST, bytecode emit, interpret bytecode).
    with open(fullpath) as f:
        contents = f.read()

    module_code = compile(contents, fullpath, 'exec')
    assert isinstance(module_code, types.CodeType), module_code

    globals_ = {
        '__builtins__': builtins,
        '__name__': fully_qualified,
    }
    module = GuestModule(module_name, code=module_code, globals_=globals_,
                         filename=fullpath)
    logging.debug('fully_qualified: %r module: %r', fully_qualified, module)
    state.sys_modules[fully_qualified] = module
    result = interp(module_code, globals_=globals_, in_function=False,
                    state=state)
    if result.is_exception():
        return result
    return Result(module)


def _do_import(name: Text,
               *,
               fully_qualified: Text,
               globals_: Dict[Text, Any],
               interp, state: InterpreterState,
               more_paths: List[Text],
               module_path: Optional[Text] = None) -> Result[ModuleT]:
    def import_error(name: Text) -> Result[Any]:
        return Result(ExceptionData(
            None,
            'Could not find module with name {!r}'.format(name),
            ImportError))

    if fully_qualified in state.sys_modules:
        logging.debug('Hit fully_qualified in sys_modules: %r',
                      fully_qualified)
        already_imported = state.sys_modules[fully_qualified]
        return Result(already_imported)

    if name in ('functools', 'os', 'sys', 'itertools', 'builtins', '_weakref'):
        module = __import__(name, globals_)  # type: types.ModuleType
    else:
        paths = [module_path] if module_path else state.paths
        assert isinstance(paths, list), paths
        all_paths = more_paths + paths
        path = find_module_path(name, all_paths)
        if path is None:
            if COLOR_TRACE:
                cprint('Attempted to import %r from paths: %r '
                       'more paths: %r' % (name, all_paths, more_paths),
                       color='red')
            return import_error(name)
        else:
            result = import_path(path, fully_qualified, interp, state=state)
            if result.is_exception():
                return result
            module = result.get_value()

    return Result(module)


def do_import(name: Text,
              *,
              interp,
              state: InterpreterState,
              globals_: Dict[Text, Any],
              more_paths: Optional[List[Text]] = None) -> Result[ModuleT]:
    """Imports a given module `name` which may have dots in it.

    Note that in the process of importing a module we import and run code for
    packages that lead up to that final module value.

    Args:
        name: Name of the module to import, may have dots in it.
        interp: Interpreter callback.
        state: Interpreter state (used for determining search paths).
        globals_: Global bindings for the import operation.

    Returns:
        The module that has been imported.
    """
    outermost = None  # type: Optional[ModuleT]
    outer = None
    more_paths = more_paths or []

    def outer_filename() -> Text:
        if isinstance(outer, types.ModuleType):
            return outer.__file__
        else:
            assert isinstance(outer, GuestModule)
            return outer.filename

    pieces = name.split('.')
    for i, piece in enumerate(pieces):
        logging.debug('Importing piece %r; outer: %r; pieces: %r', piece,
                      outer, pieces)
        module_path = (None if outer is None
                       else os.path.dirname(outer_filename()))
        new_outer = _do_import(piece, fully_qualified='.'.join(pieces[:i+1]),
                               globals_=globals_,
                               interp=interp, state=state,
                               module_path=module_path,
                               more_paths=more_paths)
        if new_outer.is_exception():
            return new_outer
        if outer:
            outer.setattr(piece, new_outer.get_value())
        outer = new_outer.get_value()
        outermost = outermost or new_outer.get_value()

    # Workaround for erroneous-seeming pytype deduction.
    def _to_result(x: ModuleT) -> Result[ModuleT]:
        return Result(x)

    assert outermost is not None
    return _to_result(outermost)


def do_subimport(module: ModuleT, name: Text, *,
                 interp, state: InterpreterState, globals_: Dict[Text, Any]):
    return do_import(name, interp=interp, state=state, globals_=globals_,
                     more_paths=[module.filename])


def resolve_level_to_dirpaths(importing_filename: Text,
                              level: int) -> List[Text]:
    # "Positive values for level indicate the number of parent
    # directories to search relative to the directory of the module
    # calling __import__() (see PEP 328 for the details)."
    #
    # -- https://docs.python.org/3.6/library/functions.html#__import__
    dirname = os.path.dirname(importing_filename)
    if level == 0:
        return [dirname]

    paths = [dirname]
    for _ in range(level-1):
        (dirname, _) = os.path.split(dirname)
        paths.append(dirname)

    # Reverse them so that we search the deepest level first.
    paths = paths[::-1]

    if COLOR_TRACE:
        cprint('Resolved level {!r} from importing filename {!r}'
               ' to paths: {!r}'.format(level, importing_filename, paths),
               color='blue')

    return paths

import builtins
import logging
import os
import sys
import types
from typing import Text, Dict, Any, Optional, Union, Sequence

from interp_result import Result, ExceptionData
from interpreter_state import InterpreterState
from guest_objects import GuestModule


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
                     path: Optional[Text] = None) -> Optional[Text]:
    pieces = name.split('.')
    paths = sys.path if path is None else [path]

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

    globals_ = {'__builtins__': builtins}
    module = GuestModule(module_name, code=module_code, globals_=globals_,
                         filename=fullpath)
    logging.debug('fully_qualified: %r module: %r', fully_qualified, module)
    state.sys_modules[fully_qualified] = module
    interp(module_code, globals_=globals_, in_function=False, state=state)
    return Result(module)


def _do_import(name: Text,
               *,
               fully_qualified: Text,
               globals_: Dict[Text, Any],
               interp, state: InterpreterState,
               module_path: Optional[Text] = None) -> Result[
                Union[types.ModuleType, GuestModule]]:
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

    if name in ('functools', 'os', 'itertools', 'builtins'):
        module = __import__(name, globals_)  # type: types.ModuleType
    else:
        path = find_module_path(name, module_path)
        if path is None:
            return import_error(name)
        else:
            result = import_path(path, fully_qualified, interp, state=state)
            if result.is_exception():
                raise NotImplementedError
            module = result.get_value()

    return Result(module)


def do_import(name: Text,
              *,
              interp, state: InterpreterState,
              globals_: Dict[Text, Any]) -> Result[
                Union[types.ModuleType, GuestModule]]:
    """Imports a given module `name` which may have dots in it."""
    assert name, 'Name to import must not be empty.'
    outermost = None  # type: Optional[Union[types.ModuleType, GuestModule]]
    outer = None

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
                               module_path=module_path)
        if new_outer.is_exception():
            return new_outer
        if outer:
            outer.setattr(piece, new_outer.get_value())
        outer = new_outer.get_value()
        outermost = outermost or new_outer.get_value()

    # Workaround for erroneous-seeming pytype deduction.
    def _to_result(x: Union[types.ModuleType, GuestModule]) -> Result[
            Union[types.ModuleType, GuestModule]]:
        return Result(x)

    assert outermost is not None
    return _to_result(outermost)

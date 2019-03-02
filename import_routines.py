import builtins
import logging
import os
import sys
from types import ModuleType, CodeType
from typing import (
    Text, Dict, Any, Optional, Union, Sequence, List, Tuple, Callable,
)

from interp_result import Result, ExceptionData
from interpreter_state import InterpreterState
from guest_objects import GuestModule

from termcolor import cprint


COLOR_TRACE_LEVEL = -1
SPECIAL_MODULES = (
    'functools', 'os', 'sys', 'itertools', 'builtins', '_weakref',
)


ModuleT = Union[ModuleType, GuestModule]


def ctimport(msg, level=0):
    if level <= COLOR_TRACE_LEVEL:
        cprint('import: %s' % msg, color='yellow', file=sys.stderr)


def _import_module_at_path(path: Text,
                           fully_qualified_name: Text,
                           state: InterpreterState,
                           interp) -> Result[GuestModule]:
    """Imports a module at the given path and runs its code.

    * Reads in the file,
    * Starts the module existing in the interpreter state, and
    * Evaluates the code contained inside the file within that module
      namespace.

    Returns:
        The imported module in a Result wrapper.
    """
    assert isinstance(fully_qualified_name, str), fully_qualified_name
    ctimport(' _import_module_at_path; path: %r; fully_qualified_name: %r' % (
                path, fully_qualified_name))

    if fully_qualified_name in state.sys_modules:
        return Result(state.sys_modules[fully_qualified_name])

    with open(path) as f:
        contents = f.read()
    module_code = compile(contents, path, 'exec')
    assert isinstance(module_code, CodeType), module_code

    globals_ = {
        '__builtins__': builtins,
        '__name__': fully_qualified_name,
        '__file__': path,
    }
    if path.endswith('__init__.py'):
        globals_['__path__'] = [os.path.dirname(path)]

    module = GuestModule(
        fully_qualified_name, code=module_code, globals_=globals_,
        filename=path)
    state.sys_modules[fully_qualified_name] = module
    result = interp(module_code, globals_=globals_, in_function=False,
                    state=state)
    if result.is_exception():
        return result
    return Result(module)


def _subimport_module_at_path(path: Text,
                              fully_qualified_name: Text,
                              containing_package: GuestModule,
                              state: InterpreterState,
                              interp) -> Result[GuestModule]:
    assert isinstance(fully_qualified_name, str), fully_qualified_name
    mod_result = _import_module_at_path(
        path, fully_qualified_name, state, interp)
    if mod_result.is_exception():
        return mod_result

    module_name = fqn_suffix(fully_qualified_name)
    ctimport(' _subimport_module_at_path; setting attr %r to %r' % (
                module_name, mod_result.get_value()))
    containing_package.setattr(module_name, mod_result.get_value())
    return mod_result


def _resolve_module_or_package(dirpath: Text,
                               fqn_piece: Text) -> Result[Text]:
    ctimport('  _resolve_module_or_package; dirpath: {!r}; '
             'fqn_piece: {!r}'.format(
                 dirpath, fqn_piece))
    module_path = os.path.join(dirpath, fqn_piece + '.py')
    package_path = os.path.join(dirpath, fqn_piece, '__init__.py')
    if os.path.exists(module_path):
        return Result(module_path)
    if os.path.exists(package_path):
        return Result(package_path)
    return Result(ExceptionData(
        None,
        'Could not find module or package with name: {!r}'.format(fqn_piece),
        ImportError))


def _find_absolute_import_path(module_name: Text,
                               search_paths: Sequence[Text]) -> Result[Text]:
    for path in search_paths:
        module_path = _resolve_module_or_package(path, module_name)
        if not module_path.is_exception():
            ctimport('  _find_absolute_import_path: {!r}'.format(module_path))
            return module_path
    return Result(ExceptionData(
        None,
        'Could not find absolute import for '
        'package with name: {!r}'.format(module_name),
        ImportError))


def getattr_or_subimport(current_mod: GuestModule,
                         fromlist_name: Text,
                         state: InterpreterState, interp) -> Result[Any]:
    ctimport('Attempting to getattr %r from %r' % (fromlist_name, current_mod))
    result = current_mod.getattr(fromlist_name)
    if not result.is_exception():
        return result

    current_dirpath = os.path.dirname(current_mod.filename)
    path_result = _resolve_module_or_package(current_dirpath, fromlist_name)
    if path_result.is_exception():
        return Result(path_result.get_exception())
    path = path_result.get_value()

    return _subimport_module_at_path(
        path, fqn_join(current_mod.fully_qualified_name, fromlist_name),
        current_mod, state, interp)


def _extract_fromlist(start_module: ModuleT,
                      module: ModuleT,
                      fromlist: Optional[Sequence[Text]],
                      state: InterpreterState,
                      interp) -> Result[Tuple[Any, ...]]:
    if fromlist is None or fromlist == ('*',):
        return Result((start_module, module, ()))

    results = []  # List[Any]
    for name in fromlist:
        ctimport('resolving fromlist name %r against %r' % (name, module))
        result = getattr_or_subimport(module, name, state, interp)
        if result.is_exception():
            return Result(result.get_exception())
        results.append(result.get_value())

    return Result((start_module, module, tuple(results)))


def check_fqn(x: Text) -> Text:
    pieces = x.split('.')
    assert all(piece for piece in pieces), x
    return '.'.join(pieces)


def fqn_parent(x: Text, path: Text = '') -> Text:
    if os.path.basename(path) == '__init__.py':
        return x
    return '.'.join(x.split('.')[:-1])


def fqn_suffix(x: Text) -> Text:
    return x.split('.')[-1]


def fqn_join(x: Text, y: Text) -> Text:
    if not y:
        return x
    ctimport('   fqn_join; x: %r; y: %r' % (x, y))
    return check_fqn(x + '.' + y)


def _traverse_module_pieces(
        current_mod: ModuleT, current_dirpath: Text,
        multi_module_pieces: Tuple[Text], state: InterpreterState,
        interp) -> Result[ModuleT]:
    # Iterate through the "pieces" to import, advancing current_mod as we go.
    for i, piece in enumerate(multi_module_pieces):
        path_result = _resolve_module_or_package(current_dirpath, piece)
        if path_result.is_exception():
            return Result(path_result.get_exception())
        path = path_result.get_value()

        fqn = fqn_join(current_mod.fully_qualified_name, piece)
        ctimport(' traversed to module: %r; subimporting path: %r' % (
                    fqn, path))
        assert isinstance(fqn, str), fqn
        new_mod = _subimport_module_at_path(
            path, fqn, current_mod, state, interp)
        if new_mod.is_exception():
            return Result(new_mod.get_exception())
        current_dirpath = os.path.dirname(path)
        current_mod = new_mod.get_value()

    return Result(current_mod)


def _resolve_level(
        importing_path: Text,
        importing_fully_qualified_name: Text,
        level: int) -> Tuple[Text, Text]:
    """
    Returns (start_path, fqn_prefix).
    """
    assert level > 0, level
    path = os.path.join(os.path.dirname(importing_path), '__init__.py')
    fqn_prefix = (importing_fully_qualified_name
                  if os.path.basename(importing_path) == '__init__.py'
                  else fqn_parent(importing_fully_qualified_name))
    for _ in range(level-1):
        path = os.path.join(os.path.dirname(os.path.dirname(path)),
                            '__init__.py')
        fqn_prefix = fqn_parent(fqn_prefix)

    return (path, fqn_prefix)


def _ascend_to_target_package(level: int, importing_path: Text,
                              importing_fqn: Text, state: InterpreterState,
                              interp) -> Result[Tuple[ModuleT, Text]]:
    def to_package(path, fqn):
        if os.path.basename(path) == '__init__.py':
            return path, fqn
        return (os.path.join(os.path.dirname(path), '__init__.py'),
                fqn_parent(fqn))

    def parent(path, fqn):
        assert os.path.basename(path) == '__init__.py'
        return (os.path.join(os.path.dirname(os.path.dirname(path)),
                             '__init__.py'),
                fqn_parent(fqn))

    path, fqn = to_package(importing_path, importing_fqn)
    for _ in range(level-1):
        path, fqn = parent(path, fqn)

    import_result = _import_module_at_path(path, fqn, state, interp)
    if import_result.is_exception():
        return Result(import_result.get_exception())
    return Result((import_result.get_value(), os.path.dirname(path)))


def _import_name_with_level(
        multi_module_name: Text,
        level: int,
        fromlist: Optional[Tuple[Text]],
        importing_path: Text,
        importing_fully_qualified_name: Text,
        state: InterpreterState,
        interp) -> Result[Tuple[ModuleT, ModuleT, Tuple[Any, ...]]]:
    start_mod_result = _ascend_to_target_package(
        level, importing_path, importing_fully_qualified_name, state, interp)
    if start_mod_result.is_exception():
        return Result(start_mod_result.get_exception())
    start_mod, start_dirpath = start_mod_result.get_value()

    multi_module_pieces = tuple(multi_module_name.split('.'))
    current_mod = _traverse_module_pieces(
        start_mod, start_dirpath, multi_module_pieces, state, interp)
    if current_mod.is_exception():
        return Result(current_mod.get_exception())

    return _extract_fromlist(start_mod, current_mod.get_value(), fromlist,
                             state, interp)


def _import_name_without_level(
        multi_module_name: Text,
        fromlist: Optional[Tuple[Text]],
        importing_path: Text,
        importing_fully_qualified_name: Text,
        search_paths: Sequence[Text],
        state: InterpreterState,
        interp) -> Result[Tuple[ModuleT, ModuleT, Tuple[Any, ...]]]:
    multi_module_pieces = tuple(multi_module_name.split('.'))
    start_path_result = _find_absolute_import_path(multi_module_pieces[0],
                                                   search_paths)
    if start_path_result.is_exception():
        return Result(start_path_result.get_exception())
    start_path = start_path_result.get_value()
    start_fqn = multi_module_pieces[0]
    ctimport(' _import_name_without_level; '
             'start_path: {!r}; start_fqn: {!r}'.format(start_path, start_fqn))

    # First import the "start path" as the first module-or-package.
    start_mod_result = _import_module_at_path(
        start_path, start_fqn, state, interp)
    if start_mod_result.is_exception():
        return Result(start_mod_result.get_exception())
    start_mod = start_mod_result.get_value()
    start_dirpath = os.path.dirname(start_path)

    ctimport(' _import_name; traversing from start_dirpath: %r '
             'via multi_module_pieces: %r' % (
                 start_dirpath, multi_module_pieces))

    # Then traverse from that "start module" via the multi_module_pieces.
    current_mod = _traverse_module_pieces(
        start_mod, start_dirpath, multi_module_pieces[1:], state, interp)
    if current_mod.is_exception():
        return Result(current_mod.get_exception())

    ctimport(' _import_name: resolved mod: %r' % (current_mod,))
    return _extract_fromlist(start_mod, current_mod.get_value(), fromlist,
                             state, interp)


def _import_name(multi_module_name: Text,
                 level: int,
                 fromlist: Optional[Sequence[Text]],
                 importing_path: Text,
                 importing_fully_qualified_name: Text,
                 search_paths: Sequence[Text],
                 state: InterpreterState,
                 interp) -> Result[Tuple[ModuleT, ModuleT, Tuple[Any, ...]]]:
    """Acts similarly to the IMPORT_NAME bytecode.

    Args:
        level: Represents the number of dots leading from "from" part of the
            import; e.g. in "from ..foo.bar.baz import bat" the level is 2.
        multi_module_name: The string "to the left of the 'import' keyword";
            e.g. in "from ..foo.bar.baz import bat" the multi_module_name is
            "foo.bar.baz".

    Returns:
        A result-wrapper over (imported_module, fromlist_values).
    """
    if level:
        return _import_name_with_level(
            multi_module_name, level, fromlist, importing_path,
            importing_fully_qualified_name, state, interp)
    else:
        return _import_name_without_level(
            multi_module_name, fromlist, importing_path,
            importing_fully_qualified_name, search_paths, state, interp)


def import_path(path: Text, module_name: Text, fully_qualified_name: Text,
                state: InterpreterState, interp) -> Result[ModuleT]:
    if fully_qualified_name in state.sys_modules:
        return Result(state.sys_modules[fully_qualified_name])
    return _import_module_at_path(path, fully_qualified_name, state, interp)


def run_IMPORT_NAME(importing_path: Text,
                    level: int,
                    fromlist: Optional[Tuple[Text, ...]],
                    multi_module_name: Text,
                    globals_: Dict[Text, Any],
                    interp, state: InterpreterState) -> Result[Any]:
    ctimport('IMPORT_NAME; multi_module_name: %r; importing_path: %r; '
             'level: %r; fromlist: %r' % (
                multi_module_name, importing_path, level, fromlist))

    if multi_module_name in state.sys_modules:
        return Result(state.sys_modules[multi_module_name])

    if multi_module_name in SPECIAL_MODULES:
        module = __import__(multi_module_name, globals_)  # type: ModuleType
        result = _extract_fromlist(module, module, fromlist, state, interp)
    else:
        result = _import_name(multi_module_name, level, fromlist,
                              importing_path, globals_['__name__'],
                              state.paths, state, interp)

    if result.is_exception():
        return result

    root, leaf, fromlist_values = result.get_value()

    if fromlist is None:
        return Result(root)

    if fromlist == ('*',):
        import_star(leaf, globals_)
    else:
        for name, value in zip(fromlist, fromlist_values):
            globals_[name] = value

    return Result(leaf)


def import_star(module, globals_):
    for name in module.keys():
        ctimport('import_star; module key: %r' % name)
        if not name.startswith('_'):
            globals_[name] = module.getattr(name).get_value()

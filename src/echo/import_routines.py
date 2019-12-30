import importlib
import functools
import logging
import os
import sys
from types import ModuleType, CodeType
from typing import (
    Text, Dict, Any, Optional, Union, Sequence, List, Tuple, Callable,
)

from echo.elog import log as elog
from echo.interp_context import ICtx
from echo.interp_result import Result, ExceptionData
from echo.emodule import EModule

from termcolor import cprint


DEBUG_PRINT_IMPORTS = bool(os.getenv('DEBUG_PRINT_IMPORTS', False))
SPECIAL_MODULES = (
    'os', 'sys', 'itertools', 'time',
    '_weakref', '_weakrefset', '_thread', 'errno', '_sre',
    '_struct', '_codecs',
    'numpy.core._multiarray_umath',
)


ModuleT = Union[ModuleType, EModule]


def _bump_import_depth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        ictx = kwargs['ictx']
        assert isinstance(ictx, ICtx), ictx
        ictx.interp_state.import_depth += 1
        try:
            result = f(*args, **kwargs)
        finally:
            ictx.interp_state.import_depth -= 1
        return result
    return wrapper


def log(ictx: ICtx, s: Text) -> None:
    if not DEBUG_PRINT_IMPORTS:
        return
    leader = '| ' * ictx.interp_state.import_depth
    print(f'[impr] {leader}{s}',
          file=sys.stderr)


@_bump_import_depth
def _import_module_at_path(
        path: Text, fully_qualified_name: Text, *,
        ictx: ICtx) -> Result[EModule]:
    """Imports a module at the given path and runs its code.

    * Reads in the file,
    * Starts the module existing in the interpreter state, and
    * Evaluates the code contained inside the file within that module
      namespace.

    Returns:
        The imported module in a Result wrapper.
    """
    assert isinstance(path, str), path
    if fully_qualified_name in ictx.interp_state.sys_modules:
        return Result(ictx.interp_state.sys_modules[fully_qualified_name])

    log(ictx, f'importing module {fully_qualified_name} at path {path}')

    with open(path) as f:
        contents = f.read()

    # Compile the module contents and wrap it up as a EModule.
    module_code = compile(contents, path, 'exec')
    assert isinstance(module_code, CodeType), module_code

    globals_ = {
        '__builtins__': ictx.get_ebuiltins(),
        '__name__': fully_qualified_name,
        '__file__': path,
    }
    if path.endswith('__init__.py'):
        globals_['__path__'] = [os.path.dirname(path)]

    module = EModule(
        fully_qualified_name, globals_=globals_, filename=path)

    # Place the imported module into the module dictionary.
    ictx.interp_state.sys_modules[fully_qualified_name] = module

    # Run the code within the module.
    result = ictx.interp_callback(
        module_code, globals_=globals_, in_function=False,
        name=fully_qualified_name, ictx=ictx)
    if result.is_exception():
        return result

    log(ictx, f'done importing module {fully_qualified_name} at path {path}')
    return Result(module)


def _subimport_module_at_path(
        path: Text, fully_qualified_name: Text,
        containing_package: EModule, ictx: ICtx) -> Result[EModule]:
    assert isinstance(containing_package, EModule), module
    log(ictx, f'path {path} fqn {fully_qualified_name} '
              f'containing_package {containing_package}')

    mod_result = _import_module_at_path(path, fully_qualified_name, ictx=ictx)
    if mod_result.is_exception():
        return mod_result

    module_name = fqn_suffix(fully_qualified_name)
    res = containing_package.setattr(
        module_name, mod_result.get_value(), ictx)
    if res.is_exception():
        return Result(res.get_exception())
    return mod_result


def _resolve_module_or_package(
        dirpath: Text, fqn_piece: Text) -> Result[Text]:
    elog('imp:rmop',
         f'resolving mod or pkg; dirpath {dirpath!r} fqn_piece {fqn_piece!r}')
    module_path = os.path.join(dirpath, fqn_piece + '.py')
    package_path = os.path.join(dirpath, fqn_piece, '__init__.py')
    if os.path.exists(module_path):
        return Result(module_path)
    if os.path.exists(package_path):
        return Result(package_path)

    msg = 'Could not find module or package with name: {!r}'.format(fqn_piece),
    return Result(ExceptionData(
        None,
        None,
        ImportError(msg)))


def _find_absolute_import_path(module_name: Text,
                               search_paths: Sequence[Text]) -> Result[Text]:
    for path in search_paths:
        module_path = _resolve_module_or_package(path, module_name)
        if not module_path.is_exception():
            return module_path
    msg = 'Could not find absolute import for package with name: {!r}'.format(
        module_name)
    return Result(ExceptionData(
        None,
        None,
        ImportError(msg)))


def _getattr_or_subimport(current_mod: ModuleT,
                          fromlist_name: Text,
                          ictx: ICtx) -> Result[Any]:
    """Either gets an attribute from a module or attempts a sub-import if no
    such attribute is available."""
    log(ictx, f'_getattr_or_subimport; current_mod: {current_mod} '
              f'fromlist_name: {fromlist_name}')

    # Try normal gettattr for real Python modules.
    if isinstance(current_mod, ModuleType):
        return Result(getattr(current_mod, fromlist_name))

    # Use echo getattr for EModules.
    assert isinstance(current_mod, EModule), current_mod
    result = current_mod.getattr(fromlist_name, ictx)
    if not result.is_exception():
        return result

    # If not an attribute, try a sub-import.
    current_dirpath = os.path.dirname(current_mod.filename)
    path_result = _resolve_module_or_package(current_dirpath, fromlist_name)
    if path_result.is_exception():
        return Result(path_result.get_exception())
    path = path_result.get_value()

    return _subimport_module_at_path(
        path, fqn_join(current_mod.fully_qualified_name, fromlist_name),
        current_mod, ictx)


def _extract_fromlist(
        start_module: ModuleT,
        module: ModuleT,
        fromlist: Optional[Sequence[Text]],
        ictx: ICtx) -> Result[Tuple[Any, ...]]:
    """Returns (start_module, leaf_module, fromlist_imports)."""
    if fromlist is None or fromlist == ('*',):
        return Result((start_module, module, ()))

    results = []  # List[Any]
    for name in fromlist:
        result = _getattr_or_subimport(module, name, ictx)
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
    return check_fqn(x + '.' + y)


def _traverse_module_pieces(
        current_mod: ModuleT, current_dirpath: Text,
        multi_module_pieces: Tuple[Text], ictx: ICtx) -> Result[ModuleT]:
    # Iterate through the "pieces" to import, advancing current_mod as we go.
    for i, piece in enumerate(multi_module_pieces):
        path_result = _resolve_module_or_package(current_dirpath, piece)
        if path_result.is_exception():
            return Result(path_result.get_exception())
        path = path_result.get_value()

        fqn = fqn_join(current_mod.fully_qualified_name, piece)
        assert isinstance(fqn, str), fqn
        new_mod = _subimport_module_at_path(
            path, fqn, current_mod, ictx)
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


def _ascend_to_target_package(
        level: int, importing_path: Text, importing_fqn: Text,
        ictx: ICtx) -> Result[Tuple[ModuleT, Text]]:
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

    import_result = _import_module_at_path(
        path, fqn, ictx=ictx)
    if import_result.is_exception():
        return Result(import_result.get_exception())
    return Result((import_result.get_value(), os.path.dirname(path)))


def _import_name_with_level(
        multi_module_name: Text,
        level: int,
        fromlist: Optional[Tuple[Text]],
        importing_path: Text,
        importing_fully_qualified_name: Text,
        ictx: ICtx
            ) -> Result[Tuple[ModuleT, ModuleT, Tuple[Any, ...]]]:
    start_mod_result = _ascend_to_target_package(
        level, importing_path, importing_fully_qualified_name, ictx)
    if start_mod_result.is_exception():
        return Result(start_mod_result.get_exception())
    start_mod, start_dirpath = start_mod_result.get_value()

    multi_module_pieces = tuple(multi_module_name.split('.'))
    current_mod = _traverse_module_pieces(
        start_mod, start_dirpath, multi_module_pieces, ictx)
    if current_mod.is_exception():
        return Result(current_mod.get_exception())

    return _extract_fromlist(start_mod, current_mod.get_value(), fromlist,
                             ictx)


def _import_name_without_level(
        multi_module_name: Text,
        fromlist: Optional[Tuple[Text]],
        importing_path: Text,
        importing_fully_qualified_name: Text,
        search_paths: Sequence[Text],
        ictx: ICtx
            ) -> Result[Tuple[ModuleT, ModuleT, Tuple[Any, ...]]]:
    multi_module_pieces = tuple(multi_module_name.split('.'))
    start_path_result = _find_absolute_import_path(multi_module_pieces[0],
                                                   search_paths)
    if start_path_result.is_exception():
        return Result(start_path_result.get_exception())
    start_path = start_path_result.get_value()
    start_fqn = multi_module_pieces[0]

    # First import the "start path" as the first module-or-package.
    start_mod_result = _import_module_at_path(
        start_path, start_fqn, ictx=ictx)
    if start_mod_result.is_exception():
        return Result(start_mod_result.get_exception())
    start_mod = start_mod_result.get_value()
    start_dirpath = os.path.dirname(start_path)

    # Then traverse from that "start module" via the multi_module_pieces.
    current_mod = _traverse_module_pieces(
        start_mod, start_dirpath, multi_module_pieces[1:], ictx)
    if current_mod.is_exception():
        return Result(current_mod.get_exception())

    return _extract_fromlist(start_mod, current_mod.get_value(), fromlist,
                             ictx)


def _import_name(multi_module_name: Text,
                 level: int,
                 fromlist: Optional[Sequence[Text]],
                 importing_path: Text,
                 importing_fully_qualified_name: Text,
                 search_paths: Sequence[Text],
                 ictx: ICtx,
                 ) -> Result[Tuple[ModuleT, ModuleT, Tuple[Any, ...]]]:
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
            importing_fully_qualified_name, ictx)
    else:
        return _import_name_without_level(
            multi_module_name, fromlist, importing_path,
            importing_fully_qualified_name, search_paths, ictx)


def import_path(path: Text, module_name: Text, fully_qualified_name: Text,
                ictx: ICtx) -> Result[ModuleT]:
    if fully_qualified_name in ictx.interp_state.sys_modules:
        return Result(ictx.interp_state.sys_modules[fully_qualified_name])
    return _import_module_at_path(path, fully_qualified_name, ictx=ictx)


def run_IMPORT_FROM(module: ModuleT, fromname: Text, ictx: ICtx):
    return _getattr_or_subimport(module, fromname, ictx)


def run_IMPORT_NAME(importing_path: Text,
                    level: int,
                    fromlist: Optional[Tuple[Text, ...]],
                    multi_module_name: Text,
                    globals_: Dict[Text, Any],
                    ictx: ICtx,
                    ) -> Result[Any]:
    """Performs functionality of the IMPORT_NAME bytecode.

    Args:
        importing_path: The filename for the code object that's doing the
            IMPORT_NAME.
        level: TODO document
        fromlist: TODO document
        multi_module_name: TODO document
        globals_: Globals for the *importing* module.
        ictx: Interpreter context.

    Returns:
        The imported module.

    Side effects:
        Imports indicated names (based on the fromlist) into the globals_ for
        the importing module.
    """
    log(ictx, 'run_IMPORT_NAME importing_path {} level {} fromlist {} '
              'multi_module_name {}'.format(
                importing_path, level, fromlist, multi_module_name))

    # If it has already been imported, we just give back that result.
    if multi_module_name in ictx.interp_state.sys_modules:
        return Result(ictx.interp_state.sys_modules[multi_module_name])

    if multi_module_name in ('_abc', '_heapq'):
        # Some C modules we refuse to import so we can get their Python based
        # implementations instead.
        msg = 'Cannot import C-module {}.'.format(multi_module_name)
        return Result(ExceptionData(
            None, None, ImportError(msg)))
    elif multi_module_name in SPECIAL_MODULES:
        module = importlib.import_module(multi_module_name)
        assert isinstance(module, ModuleType), module
        result = _extract_fromlist(module, module, fromlist, ictx)
    else:
        result = _import_name(
            multi_module_name, level, fromlist, importing_path,
            globals_['__name__'], ictx.interp_state.paths, ictx)

    if result.is_exception():
        return result

    log(ictx, 'run_IMPORT_NAME result: {}'.format(result.get_value()))
    root, leaf, fromlist_values = result.get_value()

    if fromlist is None:
        return Result(root)

    if fromlist == ('*',):
        import_star(leaf, globals_, ictx)
    else:
        for name, value in zip(fromlist, fromlist_values):
            globals_[name] = value

    return Result(leaf)


def import_star(module: ModuleT,
                globals_: Dict[Text, Any],
                ictx: ICtx,
                ) -> None:
    if isinstance(module, ModuleType):
        for name in dir(module):
            if not name.startswith('_'):
                globals_[name] = getattr(module, name)
    else:
        assert isinstance(module, EModule), module
        for name in module.keys():
            if not name.startswith('_'):
                globals_[name] = module.getattr(name, ictx).get_value()

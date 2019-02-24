import builtins
import logging
import os
import sys
import types
from typing import Text, Dict, Any, Optional, Union, Sequence, List, Tuple

from interp_result import Result, ExceptionData
from interpreter_state import InterpreterState
from guest_objects import GuestModule

from termcolor import cprint


COLOR_TRACE = False


ModuleT = Union[types.ModuleType, GuestModule]


def ctimport(msg):
    if COLOR_TRACE:
        cprint('import: %s' % msg, color='yellow', file=sys.stderr)


def _find_module_path(search_path: Text,
                      pieces: Sequence[Text]) -> Optional[Text]:
    *leaders, last = pieces
    candidate = os.path.join(search_path, *leaders)
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
    """Machinery for importing module code at a known path.

    * Reads the file contents.
    * Compiles the file contents to a code object.
    * Creates a GuestModule that wraps the code object.
    * Places that module into the interpreter state (sys.modules).
    * Interprets the code object with the module object's dictionary as
      globals.
    """
    ctimport('import_path; path: %r' % path)
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
        '__file__': path,
    }
    module = GuestModule(module_name, code=module_code, globals_=globals_,
                         filename=fullpath)
    ctimport('import_path; fully_qualified: %r module: %r' % (
                fully_qualified, module))
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
    """Attempts to import "name" using the given paths.

    * Attempts to resolve fully_qualified in the interpreter state.
    * Finds a path for a module with "name" using more_paths in priority order.
      Note that, if module_path is provided, it is used in lieu of the
      "interpreter state" paths (i.e. sys.path).
    """
    def import_error(name: Text) -> Result[Any]:
        return Result(ExceptionData(
            None,
            'Could not find module with name {!r}'.format(name),
            ImportError))

    if fully_qualified in state.sys_modules:
        ctimport('_do_import; hit fully_qualified in sys_modules: %r' %
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
            ctimport('_do_import; attempted to import %r from paths: %r '
                     'more paths: %r' % (name, all_paths, more_paths))
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
              want_outermost: bool,
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
    ctimport('do_import; name: %r; more_paths: %r' % (name, more_paths))

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
        ctimport('do_import; importing piece %d: %r; full name: %r; '
                 'outer: %r; pieces: %r' % (i, piece, name, outer, pieces))
        module_path = (None if outer is None
                       else os.path.dirname(outer_filename()))
        new_outer = _do_import(piece, fully_qualified='.'.join(pieces[:i+1]),
                               globals_=globals_,
                               interp=interp, state=state,
                               module_path=module_path,
                               more_paths=more_paths)
        ctimport('do_import; imported piece %d: %r; outer: %r; '
                 'new_outer: %r' % (i, piece, outer, new_outer))
        if new_outer.is_exception():
            if outer and i+1 == len(pieces):
                ctimport('do_import; attempting to retrieve %r '
                         'as an attribute on %r' % (piece, outer))
                result = outer.getattr(piece)
                if not result.is_exception():
                    return result
            return new_outer
        if outer:
            ctimport('do_import: setting attribute %r on %r to %r' % (
                        piece, outer, new_outer.get_value()))
            outer.setattr(piece, new_outer.get_value())
        outer = new_outer.get_value()
        outermost = outermost or new_outer.get_value()

    # Workaround for erroneous-seeming pytype deduction.
    def _to_result(x: ModuleT) -> Result[ModuleT]:
        return Result(x)

    if want_outermost:
        assert outermost is not None
        return _to_result(outermost)
    else:
        assert outer is not None
        return _to_result(outer)


def do_subimport(module: ModuleT, name: Text, *,
                 interp, state: InterpreterState, globals_: Dict[Text, Any]):
    return do_import(name, interp=interp, state=state, globals_=globals_,
                     more_paths=[module.filename], want_outermost=False)


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

    ctimport('Resolved level {!r} from importing filename {!r}'
             ' to paths: {!r}'.format(level, importing_filename, paths))

    return paths


def _module_getattr(module: Union[types.ModuleType, GuestModule],
                    name: Text) -> Result[Any]:
    if isinstance(module, GuestModule):
        return module.getattr(name)
    return Result(getattr(module, name))


def import_star(module, globals_):
    for name in module.keys():
        ctimport('import_star; module key: %r' % name)
        if not name.startswith('_'):
            globals_[name] = module.getattr(name).get_value()


def run_IMPORT_NAME(importing_filename: Text, level: int,
                    fromlist: Optional[Tuple[Text, ...]], module_name: Text,
                    globals_: Dict[Text, Any], interp, state) -> Result[Any]:
    more_paths = resolve_level_to_dirpaths(importing_filename, level)
    ctimport('IMPORT_NAME; module_name: %r; more_paths: %r; fromlist: %r' % (
                module_name, more_paths, fromlist))
    result = do_import(
        module_name, globals_=globals_, interp=interp, state=state,
        more_paths=more_paths, want_outermost=fromlist is None)
    ctimport('IMPORT_NAME; result: %r' % result)
    if result.is_exception():
        return result

    if fromlist is None:
        return result

    # Not an exception.
    module = result.get_value()
    ctimport('IMPORT_NAME; resulting module: %r; fromlist: %r' % (
                module, fromlist))
    for name in fromlist:
        if name == '*':
            import_star(module, globals_)
        else:
            result = _module_getattr(module, name)
            if not result.is_exception():
                globals_[name] = result.get_value()
            else:
                ctimport('IMPORT_NAME; no attr %r on module %r; '
                         'attempting sub-import' % (name, module))
                # "Note that when using from package import item, the item
                # can be either a submodule (or subpackage) of the package,
                # or some other name defined in the package, like a
                # function, class or variable. The import statement first
                # tests whether the item is defined in the package; if not,
                # it assumes it is a module and attempts to load it. If it
                # fails to find it, an ImportError exception is raised."
                # -- https://docs.python.org/3/tutorial/modules.html
                result = do_subimport(
                    module, name, interp=interp, state=state,
                    globals_=globals_)
                if result.is_exception():
                    return result
                module = result.get_value()

    ctimport('IMPORT_NAME; result: %r' % module)
    return Result(module)

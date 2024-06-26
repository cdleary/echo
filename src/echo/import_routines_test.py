from echo import interp
from echo import builtin_sys_module
from echo.interp_context import ICtx
from echo.interpreter_state import InterpreterState

from echo.import_routines import (
    _find_absolute_import_path,
    _import_module_at_path, _subimport_module_at_path, _import_name,
    _resolve_level
)


def test_resolve_level():
    # Importing from a package.
    start_path, fqn_prefix = _resolve_level(
        importing_path='/root/foo/_stuff/__init__.py',
        importing_fully_qualified_name='foo.stuff',
        level=1)
    assert start_path == '/root/foo/_stuff/__init__.py'
    assert fqn_prefix == 'foo.stuff'

    # Importing from within a package.
    start_path, fqn_prefix = _resolve_level(
        importing_path='/root/foo/_stuff/ohai.py',
        importing_fully_qualified_name='foo.stuff.ohai',
        level=1)
    assert start_path == '/root/foo/_stuff/__init__.py'
    assert fqn_prefix == 'foo.stuff'

    # Importing level>1 within a package.
    start_path, fqn_prefix = _resolve_level(
        importing_path='/root/foo/_stuff/more/__init__.py',
        importing_fully_qualified_name='foo.stuff.more',
        level=3)
    assert start_path == '/root/foo/__init__.py'
    assert fqn_prefix == 'foo'


def test_sample_import_manual_procedure(fs):
    fs.create_dir('/root/foo')
    fs.create_file('/root/foo/__init__.py')

    fs.create_dir('/root/foo/bar')
    fs.create_file('/root/foo/bar/__init__.py')
    fs.create_file('/root/foo/bar/baz.py', contents='data=42')

    search_paths = ['/root']

    interp_state = InterpreterState(script_directory='/')
    esys = builtin_sys_module.make_sys_module([])
    ictx = ICtx(interp_state, interp.interp, interp.do_call, None, esys)

    assert _find_absolute_import_path(
        'foo', search_paths).get_value() == '/root/foo/__init__.py'
    foo = _import_module_at_path(
        '/root/foo/__init__.py', 'foo', ictx=ictx).get_value()
    bar = _subimport_module_at_path(
        '/root/foo/bar/__init__.py', 'foo.bar', foo,
        ictx).get_value()
    baz = _subimport_module_at_path(
        '/root/foo/bar/baz.py', 'foo.bar.baz', bar,
        ictx).get_value()

    assert foo.getattr('bar', ictx).get_value() is bar
    assert bar.getattr('baz', ictx).get_value() is baz


def test_sample_import_name(fs):
    fs.create_dir('/root/foo')
    fs.create_file('/root/foo/__init__.py')

    fs.create_dir('/root/foo/bar')
    fs.create_file('/root/foo/bar/__init__.py')
    fs.create_file('/root/foo/bar/baz.py', contents='data=42')

    interp_state = InterpreterState(script_directory='/')
    esys = builtin_sys_module.make_sys_module([])
    ictx = ICtx(interp_state, interp.interp, interp.do_call, None, esys)

    result = _import_name(
        'foo.bar.baz', level=0, fromlist=('data',),
        importing_path='/script.py', importing_fully_qualified_name='__main__',
        search_paths=['/root'], ictx=ictx)
    assert not result.is_exception()
    root, leaf, fromlist_values = result.get_value()
    assert fromlist_values == (42,)
    assert leaf.getattr('__name__', ictx).get_value() == 'foo.bar.baz'
    assert root.getattr('__name__', ictx).get_value() == 'foo'


def test_from_import_attribute(fs):
    my_script_text = """
from some_mod import func as f

assert f() == 42
"""
    some_mod_text = """
def func():
    return 42
"""
    fs.create_file('/my_script.py', contents=my_script_text)
    fs.create_file('/some_mod.py', contents=some_mod_text)

    interp_state = InterpreterState(script_directory='/')
    esys = builtin_sys_module.make_sys_module([])
    ictx = ICtx(interp_state, interp.interp, interp.do_call, None, esys)
    assert not interp.import_path(
        'my_script.py', '__main__', '__main__', ictx).is_exception()

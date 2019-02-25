import os
import textwrap

import interp
import import_routines
from interpreter_state import InterpreterState


def test_level_resolution():
    path, fqn = import_routines.resolve_level_to_dirpath(
        importing_filename='/package/subpackage1/__init__.py',
        importing_fully_qualified_name='package.subpackage1',
        level=2)
    assert (path, fqn) == ('/package', 'package')

    path, fqn = import_routines.resolve_level_to_dirpath(
        '/prefix/.virtualenvs/echo/lib/python3.6/site-packages/'
        'numpy/__init__.py', 'numpy', level=1)
    assert path, fqn == (
        '/prefix/.virtualenvs/echo/lib/python3.6/site-packages/numpy', 'numpy')

    path, fqn = import_routines.resolve_level_to_dirpath(
        importing_filename='/prefix/foo.py',
        importing_fully_qualified_name='__main__',
        level=0)
    assert (path, fqn) == (None, '__main__')


def test_pep328_example(fs):
    text = textwrap.dedent("""
    from .moduleY import spam
    from .moduleY import spam as ham
    from . import moduleY
    from ..subpackage1 import moduleY
    from ..subpackage2.moduleZ import eggs
    from ..moduleA import foo
    from ...package import bar
    from ...sys import path
    """)

    fs.create_dir('/package')
    fs.create_file('/package/__init__.py', contents='bar=0')
    fs.create_dir('/package/subpackage1')
    fs.create_file('/package/subpackage1/__init__.py')
    fs.create_file('/package/subpackage1/moduleX.py', contents=text)
    fs.create_file('/package/subpackage1/moduleY.py', contents='spam=1')
    fs.create_dir('/package/subpackage2')
    fs.create_file('/package/subpackage2/__init__.py')
    fs.create_file('/package/subpackage2/moduleZ.py',
                   contents="print('moduleZ'); eggs=2")
    fs.create_file('/package/moduleA.py', contents='foo=3')

    path = import_routines._find_module_path('/package/subpackage1',
                                             ['moduleX'])
    assert path == '/package/subpackage1/moduleX.py'
    path = import_routines._find_module_path('/package', ['moduleA'])
    assert path == '/package/moduleA.py'
    path = import_routines._find_module_path('/package', ['subpackage1'])
    assert path == '/package/subpackage1/__init__.py'

    module_x_path = '/package/subpackage1/moduleX.py'
    state = InterpreterState(script_directory=os.path.dirname(module_x_path))
    assert not interp.import_path(
        module_x_path, 'package.subpackage1.moduleX', state).is_exception()


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

    state = InterpreterState(script_directory='/')
    assert not interp.import_path(
        'my_script.py', 'my_script', state).is_exception()


def test_from_package_import_attribute(fs):
    my_script_text = """
from some_package import func as some_func

assert some_func() == 42
"""
    init_text = """
def func():
    return 42
"""
    fs.create_file('/my_script.py', contents=my_script_text)
    fs.create_dir('/some_package')
    fs.create_file('/some_package/__init__.py', contents=init_text)

    state = InterpreterState(script_directory='/')
    assert not interp.import_path(
        'my_script.py', 'my_script', state).is_exception()


def test_from_package_import_imported_attribute(fs):
    my_script_text = """
from some_package import some_func

assert some_func() == 42
"""
    init_text = """
from some_package.some_mod import func as some_func

assert some_func() == 42
"""
    some_mod_text = """
def func():
    return 42
"""

    fs.create_file('/my_script.py', contents=my_script_text)
    fs.create_dir('/some_package')
    fs.create_file('/some_package/__init__.py', contents=init_text)
    fs.create_file('/some_package/some_mod.py', contents=some_mod_text)

    state = InterpreterState(script_directory='/')
    assert not interp.import_path(
        'my_script.py', 'my_script', state).is_exception()

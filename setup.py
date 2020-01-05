from setuptools import setup, Extension

setup(
    name='echo',
    packages=['echo'],
    package_dir={'': 'src'},
    scripts=[
        'bin/echo_vm',
        'bin/echo_repl',
    ],
    ext_modules=[
        Extension('csample', ['ext/csample.c']),
    ],
)

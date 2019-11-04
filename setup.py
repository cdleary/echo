from setuptools import setup

setup(
    name='echo',
    packages=['echo'],
    package_dir={'': 'src'},
    scripts=[
        'bin/echo_vm',
        'bin/echo_repl',
    ],
)

"""Usage: %prog [options] file

Runs 'file' via the echo interpreter in a Python-driver-replacement style. For
example:

    python3 echo.py /tmp/example.py

This allows comparisons of echo versus the standard CPython interpreter driver
on the command line.
"""

import logging
import optparse
import os
import pdb
import types

from interp import interp


def run_path(fullpath):
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
    
    interp(module_code, globals(), in_function=False)


def main():
    parser = optparse.OptionParser(__doc__)
    parser.add_option('--log_level', choices=['DEBUG', 'INFO', 'WARNING'], help='Log level to use')
    parser.add_option('--pdb', action='store_true', default=False, help='Drop into PDB on error')
    opts, args = parser.parse_args()

    # Path.
    if len(args) != 1:
        parser.error('A single file argument is required')
    fullpath = args[0]

    # Options.
    if opts.log_level:
        logging.basicConfig(level=getattr(logging, opts.log_level))

    try:
        run_path(fullpath)
    except Exception as e:
        if opts.pdb:
            pdb.post_mortem(e.__traceback__)
        else:
            raise


if __name__ == '__main__':
    main()

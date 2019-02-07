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
import sys
import types

import interp


def main():
    parser = optparse.OptionParser(__doc__)
    parser.add_option('--log_level', choices=['DEBUG', 'INFO', 'WARNING'],
                      help='Log level to use')
    parser.add_option('--pdb', action='store_true', default=False,
                      help='Drop into PDB on error')
    parser.add_option('--ctrace', action='store_true', default=False,
                      help='Color call trace')
    opts, args = parser.parse_args()

    # Path.
    if len(args) != 1:
        parser.error('A single file argument is required')
    fullpath = args[0]

    # Options.
    if opts.log_level:
        logging.basicConfig(level=getattr(logging, opts.log_level))

    interp.COLOR_TRACE = opts.ctrace
    interp.COLOR_TRACE_FUNC = opts.ctrace

    globals_ = dict(globals())
    globals_['__file__'] = fullpath

    state = interp.InterpreterState(os.path.dirname(fullpath))
    state.paths += sys.path[1:]
    fully_qualified = '__main__'

    try:
        result = interp.import_path(fullpath, fully_qualified, state)
    except Exception as e:
        if opts.pdb:
            pdb.post_mortem(e.__traceback__)
        else:
            raise

    if result.is_exception():
        print(result.get_exception(), file=sys.stderr)


if __name__ == '__main__':
    main()

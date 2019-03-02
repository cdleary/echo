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
import import_routines
import bytecode_trace

from termcolor import cprint


def main():
    parser = optparse.OptionParser(__doc__)
    parser.add_option('--log_level', choices=['DEBUG', 'INFO', 'WARNING'],
                      help='Log level to use.')
    parser.add_option('--pdb', action='store_true', default=False,
                      help='Drop into PDB on error.')
    parser.add_option('--ctrace', action='store_true', default=False,
                      help='Color trace for guest interpreter.')
    parser.add_option('--ctrace-mod', action='store_true', default=False,
                      help='Color trace for module imports.')
    parser.add_option('--ctrace-stack', action='store_true', default=False,
                      help='Color trace stack push/pops.')
    parser.add_option('--dump_trace', help='Path to dump bytecode trace to.')
    opts, args = parser.parse_args()

    # Path.
    if len(args) != 1:
        parser.error('A single file argument is required')
    fullpath = os.path.realpath(args[0])

    # Options.
    if opts.log_level:
        logging.basicConfig(level=getattr(logging, opts.log_level))

    if opts.dump_trace:
        print('Collecting trace to', opts.dump_trace, '...')
        interp.TRACE_DUMPER = bytecode_trace.BytecodeTraceDumper(
            opts.dump_trace)

    interp.COLOR_TRACE = opts.ctrace
    interp.COLOR_TRACE_FUNC = opts.ctrace
    interp.COLOR_TRACE_STACK = opts.ctrace_stack
    if opts.ctrace or opts.ctrace_mod:
        import_routines.COLOR_TRACE_LEVEL = 1

    globals_ = dict(globals())
    globals_['__file__'] = fullpath

    state = interp.InterpreterState(os.path.dirname(fullpath))
    state.paths = sys.path[1:] + state.paths
    fully_qualified = '__main__'

    try:
        result = interp.import_path(fullpath, fully_qualified, fully_qualified,
                                    state)
    except Exception as e:
        if opts.pdb:
            pdb.post_mortem(e.__traceback__)
        else:
            raise

    if result.is_exception():
        cprint(str(result), color='red', file=sys.stderr)
        error = True
    else:
        print(result, file=sys.stderr)
        error = False

    if opts.dump_trace:
        print('Dumping trace to', opts.dump_trace, '...')
        interp.TRACE_DUMPER.dump()

    sys.exit(-1 if error else 0)


if __name__ == '__main__':
    main()

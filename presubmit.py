#!/usr/bin/env python

import optparse
import os
import subprocess
import sys

import termcolor


parser = optparse.OptionParser()
parser.add_option('--skip-tests', dest='do_test', action='store_false',
                  default=True, help='Skip test phase')
parser.add_option('--skip-style', dest='do_style', action='store_false', default=True, help='Skip style checks')
opts, args = parser.parse_args()


VERSION_MAJOR_MINOR = '.'.join(str(e) for e in sys.version_info[:2])

subprocess.check_call([
    'mypy',
    'src/echo/ctype_frame.py',
    'src/echo/efunction_type.py',
    'src/echo/frame_objects.py',
    'src/echo/__init__.py',
    'src/echo/import_routines.py',
    'src/echo/bc_helpers.py',
    'src/echo/builtin_build_class.py',
    'src/echo/builtin_bytearray.py',
    'src/echo/builtin_enumerate.py',
    'src/echo/builtin_exception.py',
    'src/echo/builtin_int.py',
    'src/echo/builtin_iter.py',
    'src/echo/builtin_list.py',
    'src/echo/builtin_object.py',
    'src/echo/builtin_predicates.py',
    'src/echo/builtin_str.py',
    'src/echo/builtin_super.py',
    'src/echo/builtin_sys_module.py',
    'src/echo/builtin_tuple.py',
    'src/echo/builtin_type.py',
    'src/echo/bytecode_trace.py',
    'src/echo/code_attributes.py',
    'src/echo/common.py',
    'src/echo/common_test.py',
    'src/echo/dso_objects.py',
    'src/echo/ebuiltins.py',
    'src/echo/egenerator.py',
    'src/echo/ecell.py',
    'src/echo/eclassmethod.py',
    'src/echo/elog.py',
    'src/echo/emap.py',
    'src/echo/emodule.py',
    'src/echo/eobjects.py',
    'src/echo/eproperty.py',
    'src/echo/epy_object.py',
    'src/echo/estaticmethod.py',
    'src/echo/etraceback.py',
    'src/echo/guest_objects_test.py',
    'src/echo/interp_context.py',
    'src/echo/interp_result.py',
    'src/echo/interp_routines.py',
    'src/echo/interpreter_state.py',
    'src/echo/iteration_helpers.py',
    'src/echo/oo_builtins.py',
    'src/echo/return_kind.py',
    'src/echo/trace_util.py',
    'src/echo/tracediff.py',
    'src/echo/value.py',
])
print('=== mypy ok!', file=sys.stderr)

if opts.do_style:
    print('=== pycodestyle', file=sys.stderr)
    subprocess.check_call(['pycodestyle', 'src/', 'tests/', 'bin/echo_vm'])

if opts.do_test:
    print('=== pytest', file=sys.stderr)
    subprocess.check_call(['pytest', '-k', 'not knownf'])

if opts.do_test:
    PASS_BANNER = 'PRESUBMIT PASS!'
    PASS_BANNER_LEN = len(PASS_BANNER)+2
    termcolor.cprint('=' * PASS_BANNER_LEN, color='green')
    termcolor.cprint(' ' + PASS_BANNER, color='green')
    termcolor.cprint('=' * PASS_BANNER_LEN, color='green')

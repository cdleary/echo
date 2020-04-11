#!/usr/bin/env python

import optparse
import os
import subprocess
import sys

import termcolor


parser = optparse.OptionParser()
parser.add_option('--skip-tests', dest='do_test', action='store_false',
                  default=True, help='Skip test phase')
opts, args = parser.parse_args()


VERSION_MAJOR_MINOR = '.'.join(str(e) for e in sys.version_info[:2])

subprocess.check_call([
    'mypy',
    'src/echo/bc_helpers.py',
    'src/echo/builtin_int.py',
    'src/echo/builtin_type.py',
    'src/echo/epy_object.py',
    'src/echo/dso_objects.py',
    'src/echo/builtin_str.py',
    'src/echo/builtin_predicates.py',
    'src/echo/builtin_enumerate.py',
])
print('=== mypy ok!')

subprocess.check_call(['pycodestyle', 'src/', 'tests/'])
if opts.do_test:
    subprocess.check_call(['pytest'])
subprocess.check_call([
    'pytype', '--config=pytype.cfg',
    '--python-version=%s' % VERSION_MAJOR_MINOR,
])

if opts.do_test:
    PASS_BANNER = 'PRESUBMIT PASS!'
    PASS_BANNER_LEN = len(PASS_BANNER)+2
    termcolor.cprint('=' * PASS_BANNER_LEN, color='green')
    termcolor.cprint(' ' + PASS_BANNER, color='green')
    termcolor.cprint('=' * PASS_BANNER_LEN, color='green')

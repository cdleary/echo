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
    'src/echo',
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

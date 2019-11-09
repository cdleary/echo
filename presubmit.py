#!/usr/bin/env python

import os
import subprocess
import sys

import termcolor


VERSION_MAJOR_MINOR = '.'.join(str(e) for e in sys.version_info[:2])


subprocess.check_call(['pytest'])
subprocess.check_call([
    'pytype', '--config=pytype.cfg',
    '--python-version=%s' % VERSION_MAJOR_MINOR,
])
subprocess.check_call(['pycodestyle', 'src/'])

PASS_BANNER = 'PRESUBMIT PASS!'
PASS_BANNER_LEN = len(PASS_BANNER)+2
termcolor.cprint('=' * PASS_BANNER_LEN, color='green')
termcolor.cprint(' ' + PASS_BANNER, color='green')
termcolor.cprint('=' * PASS_BANNER_LEN, color='green')

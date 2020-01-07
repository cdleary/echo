#!/usr/bin/env python3

import os
import subprocess
import sys

assert len(sys.argv) == 2

subprocess.check_call('which python3', shell=True)

with open('/tmp/echo.txt', 'w') as f:
    cmd = f"python3 ./bin/echo_vm py_samples/{sys.argv[1]}.py"
    env = dict(os.environ)
    env.update(E_PREFIX='', ECHO_DUMP_INSTS='1', PYTHONPATH=os.getcwd()+'/src:'+os.environ.get('PYTHONPATH', ''))
    print(cmd)
    print(env)
    subprocess.call(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=os.getcwd())

with open('/tmp/cpython.txt', 'w') as f:
    cmd = f'python3 ./bin/minimal_tracer.py py_samples/{sys.argv[1]}.py'
    print(cmd)
    subprocess.check_call(cmd, stdout=f, stderr=subprocess.STDOUT, shell=True, cwd=os.getcwd())

subprocess.call('vimdiff /tmp/echo.txt /tmp/cpython.txt', shell=True)

import os
import termcolor


assert os.getenv('ANSI_COLORS_DISABLED') is None
got = termcolor.colored('asdf', color='red')
assert got == '\x1b[31masdf\x1b[0m', repr(got)

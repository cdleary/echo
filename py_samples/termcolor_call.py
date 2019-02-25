import termcolor


got = termcolor.colored('asdf', color='red')
assert got == '\x1b[0m\x1b[31masdf', got

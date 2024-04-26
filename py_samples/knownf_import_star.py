from inner import *


assert value == 42
assert inner_func() == 42
assert '_ostensibly_private_func' not in globals()

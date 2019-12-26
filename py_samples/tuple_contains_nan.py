nan = float('nan')
assert nan is nan
assert (nan == nan) is False
assert (nan in (nan,)) is True

a = 'shooba'
b = 'dooba'
s = f'{a!s}{b!r}'
assert s == 'shooba\'dooba\'', s

s = f'{a:>10}'
assert s == '    shooba', repr(s)

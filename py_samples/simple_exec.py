my_globals = {}
r = exec('x = 2+2', my_globals) 
assert r is None
assert my_globals['x'] == 4, my_globals
assert 'x' not in globals()
assert 'r' in globals()

from functools import lru_cache


call_count = 0


def do_str(i):
    global call_count
    call_count += 1
    return str(i)


@lru_cache(maxsize=2)
def int_to_str(i):
    return do_str(i)



assert call_count == 0
assert int_to_str(42) == '42'
assert call_count == 1
assert int_to_str(42) == '42'
assert call_count == 1
assert int_to_str(64) == '64'
assert call_count == 2
assert int_to_str(64) == '64'
assert call_count == 2
assert int_to_str(42) == '42'
assert call_count == 2
assert int_to_str(128) == '128'
assert call_count == 3
assert int_to_str(42) == '42'
assert call_count == 3
assert int_to_str(64) == '64'
assert call_count == 4

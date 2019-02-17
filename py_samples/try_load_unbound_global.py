try:
    some_undefined_name
except NameError:
    assert True
else:
    assert False

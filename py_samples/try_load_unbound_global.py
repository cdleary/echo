try:
    some_undefined_name
except NameError as e:
    assert str(e) == 'name \'some_undefined_name\' is not defined', str(e)
else:
    assert False

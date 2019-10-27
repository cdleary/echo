import sys


try:
    raise TypeError
except TypeError:
    tb = sys.exc_info()[2]
    print(type(tb))
    print(type(tb.tb_frame))

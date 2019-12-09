import numpy

assert type(numpy.__version__) == str, numpy.__version__
two = numpy.array([2])
print(two + two)
print(numpy.__version__)

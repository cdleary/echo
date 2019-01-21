# echo

Python meta-circular evaluator.

[![Build Status](https://travis-ci.com/cdleary/echo.svg?branch=master)](https://travis-ci.com/cdleary/echo)

## Usage

The `echo.py` command line utility attempts to act like a substitute Python
driver that uses the guest interpreter instead of the host interpreter; e.g.

```
python3 echo.py /tmp/my_test.py
```

Ideally would match the results of direct invocation via the standard (host)
interpreter:

```
python3 /tmp/my_test.py
```

This is the property that echo attempts to build towards.

## Testing

py.test is driven via a configuration file in the root of the project
directory; so a developer can simply run:

```
py.test-3
```

To run particular tests with the logging level raised:

```
py.test-3 -k kwarg --log-cli-level=DEBUG
```

### Type checking

Type annotations are used where appropriate and checked via the "pytype"
command line utility:

```
pytype --config=pytype.cfg 
```

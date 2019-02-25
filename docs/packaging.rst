Packaging Notes
===============

Python packaging seems to have a decent amount of nuance to it, enough that it
seems helpful to write about the complexities in an attempt to straighten out
the ideas.

Various concepts involved:

* ``__name__``, which gets set up in a module's globals as part of the import
  process.
* ``__package__``, seems to be set on modules that belong to a package; e.g. if
  I have ``mypackage.subpackage.moduleA`` the ``__package__`` value in
  ``moduleA`` is ``mypackage.subpackage``.

  ::

    python -c 'from my_package.subpackage import moduleA; print(moduleA.__package__)'
    my_package.subpackage

* ``sys.modules``, where the interpreter-level state is reflected; the fact
  that modules are only imported once is visible via side-effects (e.g.
  printing when the module's code object is evaluated).
* The notion of a "fully qualified name" that is used as the key in
* ``sys.modules``, which tracks which modules should not be imported again,
  rather resolved via that bit of VM state.
* The notion of "level" for absolute import notation.
* The notion of "top-level".
* The fact that "level" import notation can turn into a "top-level" import.
* The Python path (a la ``PYTHONPATH`` env var) reflected in ``sys.path``.
* What bytecodes return; e.g. when an ``IMPORT_NAME`` of ``foo.bar.baz``
  happens does it return the ``foo`` object or ``foo.bar.baz``?
* Modules under a package implicitly tacked on in the ``__init__.py``'s
  namespace -- does it conflict with globals contained therein?
* The fact that in "from X import Y" notation the "Y" may refer either to a
  module or an item within a module.
* What forward progress is made when there are circular imports (e.g. if X at
  some point in its code imports Y, and Y imports X, then a) what happens and
  b) can Y observe the globals present in X up to the program point where it
  imported Y?)
* The originator of an import request to the VM: command line driver, import
  bytecode, ``__import__`` builtin.
  * Is there a semantically observable difference vs manually constructing a
    module object and inserting it into the system modules? Possibilities
    include things like the import hook library.
* Is the ``__main__`` script ever part of a package?
* What if the sys.path entries alias packages? E.g. if I have /foo/bar/baz.py
  as a nested set of packages, but I put and then I "import baz", "import
  bar.baz", "import foo.bar.baz" does the code for baz execute three times?
* Is the VM affected if you del ``__name__`` in the module scope or change it?
* Is relative vs absolute imports just about the prioritization of search
  paths, or is there actually a culling of possible search paths in the
  relative import case.
  * Does level denote a specific directory or a possible *set* of directories?
* The interleaving of search and evaluation; e.g. if I try to import
  foo.bar.baz and one package has foo.bar (but *not* the ``.baz`` part) earlier
  on the sys.path and another has all of foo.bar.baz but comes later on
  sys.path, it seems likely the former is attempted and raises an error, but one
  could imagine a system that separated "search for a candidate that satisfies
  the specification X.Y.Z" from its subsequent evaluation, only when all of
  "X.Y.Z" were found to be available vs greedily importing the first "X" that
  was found.


``__name__``, relative vs absolute, etc.
----------------------------------------

The ``__name__`` of the main script entry point (e.g. ``foo.py`` in
``python foo.py``) is ``__main__``, which gives rise to the
``if __name__ == "__main__"`` idiom.

If you do a bare (non-relative) import (e.g. ``import numpy``) from a
``__name__ == "__main__"`` context it seems to be conceptually a "top-level" or
"absolute" import, where the set of standard paths are searched.


PEP328 seems like it might perhaps have stale info on what is possible with
relative imports in terms of turning into these "top level" or "absolute"
imports (I hesitate to call them "absolute" if it was possible to arrive at
them via relative import syntax): there are two examples provided where
relative imports turn themselves into top-level imports by traversing beyond
the parent-most package scope, whereas in Python 3.6 this example appears to
create an error:

::

    File "/tmp/test/package/subpackage1/moduleX.py", line 7, in <module>
        from ...package import bar
    ValueError: attempted relative import beyond top-level package


IMPORT_NAME bytecode
--------------------

Fundamentally the ``IMPORT_NAME`` bytecode appears to be a function that takes:

* A module name to import.
* A "fromlist" of things to import from the resulting module.
* A "level" for relative imports within a package. When this level is 0, it is
  a "top level" or "absolute" import.

Note that if the fromlist refers to a submodule instead of an attribute it'll
attempt to do a final "sub"-import.

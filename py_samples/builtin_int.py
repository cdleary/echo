class MyClass: pass
assert int.__lt__(42, MyClass()) is NotImplemented

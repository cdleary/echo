stuff = 'this is a sentence?'
lengths = {len(p) for p in stuff.split()}
str_to_length = {p: len(p) for p in stuff.split()}
assert lengths == {1, 2, 4, 9}, lengths
assert str_to_length == {'a': 1, 'is': 2, 'this': 4, 'sentence?': 9}, str_to_length

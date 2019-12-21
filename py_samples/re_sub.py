import re

haystack = 'shooba dooba'
assert re.sub('ooba', '', haystack) == 'sh d'

import atexit
import collections
from operator import itemgetter
import pprint
from typing import Tuple, Any, Dict, Text
from echo.eobjects import EFunction, EPyObject


class CallProfiler:
    def __init__(self):
        self.profile = collections.defaultdict(collections.Counter)

    def _get_types(self, args: Tuple) -> Tuple:
        res = []
        for arg in args:
            if isinstance(arg, EPyObject):
                res.append(arg.get_type())
            else:
                res.append(type(arg))
        return tuple(res)

    def note(self, f, args: Tuple[Any, ...], kwargs: Dict[Text, Any]):
        if kwargs:
            return  # TODO
        if isinstance(f, EFunction):
            self.profile[f][self._get_types(args)] += 1

    def _code_pos(self, f):
        if isinstance(f, EFunction):
            return f'{f.code.co_filename}:{f.code.co_firstlineno}'
        else:
            raise NotImplementedError(f)

    def dump(self):
        items = []
        for f, counter in self.profile.items():
            items.append((sum(counter.values()), f, counter))
        items.sort(key=itemgetter(0), reverse=True)
        for _, f, counter in items:
            print(f'{f}: {self._code_pos(f)}')
            for sig, count in sorted(
                    counter.items(), key=itemgetter(1), reverse=True):
                print(f'  {count:8d}: {sig}')

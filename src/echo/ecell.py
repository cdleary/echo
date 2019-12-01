from typing import Text, Any


class ECell:
    def __init__(self, name: Text):
        self._name = name
        self._storage = ECell

    def __repr__(self) -> Text:
        return 'ECell(_name={!r}, _storage={})'.format(
            self._name,
            '<empty>' if self._storage is ECell else repr(self._storage))

    def initialized(self) -> bool:
        return self._storage is not ECell

    def get(self) -> Any:
        assert self._storage is not ECell, (
            'ECell %r is uninitialized' % self._name)
        return self._storage

    def set(self, value: Any) -> None:
        self._storage = value

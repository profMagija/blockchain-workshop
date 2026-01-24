import os

_STORAGE: dict[str, dict[str, bytes]] = {}


class StorageMaster:
    def __init__(self, root: str):
        self.root = root

    def get_storage(self, name: str) -> "Storage":
        if self.root == ":memory:":
            return MemoryStorage(name)
        return DiskStorage(self, name)


class Storage:
    def exists(self, path: str) -> bool: ...

    def load(self, path: str) -> bytes | None: ...

    def save(self, path: str, content: bytes): ...

    def delete(self, path: str): ...

    def __repr__(self) -> str: ...


class DiskStorage(Storage):
    def __init__(self, master: StorageMaster, name: str):
        self.master = master
        self.name = name

        if not os.path.exists(os.path.join(self.master.root, name)):
            os.makedirs(os.path.join(self.master.root, name))

    def exists(self, path: str) -> bool:
        return os.path.exists(self._make_path(path))

    def load(self, path: str) -> bytes | None:
        try:
            with open(self._make_path(path), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def save(self, path: str, content: bytes):
        with open(self._make_path(path), "wb") as f:
            f.write(content)

    def delete(self, path: str):
        os.remove(self._make_path(path))

    def _make_path(self, path: str) -> str:
        return os.path.join(self.master.root, self.name, path)

    def __repr__(self) -> str:
        return f"Storage({self.name!r})"


class MemoryStorage(Storage):
    def __init__(self, name: str):
        self.name = name
        self._storage = _STORAGE.setdefault(name, {})

    def exists(self, path: str) -> bool:
        return path in self._storage

    def load(self, path: str) -> bytes | None:
        return self._storage.get(path, None)

    def save(self, path: str, content: bytes):
        self._storage[path] = content

    def delete(self, path: str):
        del self._storage[path]

    def __repr__(self) -> str:
        return f"MemoryStorage({self.name!r})"

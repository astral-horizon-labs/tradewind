"""Mémoires locales reconstructibles, validées par leurs dépendances."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import TypeVar

T = TypeVar("T")


def file_signature(path: str | Path) -> tuple:
    """Identifie une génération locale, y compris remplacement et absence."""
    resolved = Path(path).resolve()
    try:
        state = resolved.stat()
    except FileNotFoundError:
        return (str(resolved), None)
    return (str(resolved), state.st_dev, state.st_ino, state.st_size,
            state.st_mtime_ns, state.st_ctime_ns)


def files_signature(paths: Iterable[str | Path]) -> tuple:
    """Rend l'ordre des chemins indépendant de celui d'un parcours de dossier."""
    return tuple(sorted(file_signature(path) for path in paths))


class DerivedCache:
    """Partage un calcul stable, borné en nombre de résultats et isolé des lecteurs."""

    def __init__(self, max_entries: int = 8, copy_value: Callable = deepcopy):
        if max_entries < 1:
            raise ValueError("La mémoire doit conserver au moins un résultat.")
        self._max_entries = max_entries
        self._copy_value = copy_value
        self._entries: OrderedDict[Hashable, object] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0
        self._builds = 0
        self._unstable = 0

    def get(self, key: Callable[[], Hashable], build: Callable[[], T]) -> T:
        """Relit la version sous verrou et ne conserve que les calculs stables."""
        with self._lock:
            for attempt in range(2):
                version = key()
                if version in self._entries:
                    self._hits += 1
                    self._entries.move_to_end(version)
                    return self._copy_value(self._entries[version])
                if attempt == 0:
                    self._misses += 1
                self._builds += 1
                result = build()
                if key() == version:
                    self._entries[version] = self._copy_value(result)
                    while len(self._entries) > self._max_entries:
                        self._entries.popitem(last=False)
                    return result
                self._unstable += 1
            return result

    def clear(self) -> None:
        """Vide les résultats et les compteurs, notamment pour les comparaisons."""
        with self._lock:
            self._entries.clear()
            self._hits = self._misses = self._builds = self._unstable = 0

    def info(self) -> dict[str, int]:
        """Expose les mesures locales sans changer le contrat des API métier."""
        with self._lock:
            return {"hits": self._hits, "misses": self._misses,
                    "builds": self._builds, "unstable": self._unstable,
                    "entries": len(self._entries), "max_entries": self._max_entries}

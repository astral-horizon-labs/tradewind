"""Écriture atomique et verrou exclusif d'un fichier de mémoire."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import pathlib
import tempfile
import threading

_held = threading.local()


def _lock_dir() -> pathlib.Path:
    default = pathlib.Path.home() / ".local" / "state" / "wallet" / "locks"
    return pathlib.Path(os.environ.get("WALLET_LOCK_DIR", str(default)))


def write_text(path, text: str, *, encoding: str = "utf-8") -> None:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding=encoding, dir=target.parent, prefix=f".{target.name}.",
        suffix=".tmp", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def locked(path):
    """Verrou exclusif de `path`, bloquant, relâché à la sortie du bloc."""
    target = pathlib.Path(path).resolve()
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:16]
    directory = _lock_dir()
    lock_path = directory / f"{target.name}.{digest}.lock"
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = set()
    if lock_path in held:
        yield
        return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(lock_path, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        held.add(lock_path)
        try:
            yield
        finally:
            held.discard(lock_path)
            fcntl.flock(handle, fcntl.LOCK_UN)

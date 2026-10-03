"""Cross-process coordination for memory-intensive local workloads."""

import fcntl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

ROOT = Path(__file__).resolve().parents[2]
HEAVY_RESOURCE_LOCK_PATH = ROOT / "outputs" / "heavy-worker.lock"
_PROCESS_LOCKS: dict[Path, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def _process_lock(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(resolved, threading.Lock())


class HeavyResourceLease:
    """An idempotently releasable exclusive file-lock lease."""

    def __init__(self, stream: IO[str], process_lock: threading.Lock):
        self._stream = stream
        self._process_lock = process_lock
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            if not self._stream.closed:
                fcntl.flock(self._stream, fcntl.LOCK_UN)
        finally:
            try:
                self._stream.close()
            finally:
                self._process_lock.release()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.release()


class HeavyResource:
    """Own the file lock shared by API chat and pipeline subprocess launchers."""

    def __init__(self, path: Path = HEAVY_RESOURCE_LOCK_PATH):
        self.path = path

    def acquire(self, *, blocking: bool) -> HeavyResourceLease | None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        process_lock = _process_lock(self.path)
        if not process_lock.acquire(blocking=blocking):
            return None
        stream = None
        operation = fcntl.LOCK_EX
        if not blocking:
            operation |= fcntl.LOCK_NB
        try:
            stream = self.path.open("a")
            fcntl.flock(stream, operation)
        except BlockingIOError:
            if stream is not None:
                stream.close()
            process_lock.release()
            return None
        except BaseException:
            if stream is not None:
                stream.close()
            process_lock.release()
            raise
        return HeavyResourceLease(stream, process_lock)

    @contextmanager
    def hold(self) -> Iterator[HeavyResourceLease]:
        lease = self.acquire(blocking=True)
        if lease is None:  # A blocking acquisition cannot normally return None.
            raise RuntimeError("Unable to acquire the heavy-resource lock")
        try:
            yield lease
        finally:
            lease.release()


HEAVY_RESOURCE = HeavyResource()

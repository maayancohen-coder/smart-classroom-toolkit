"""Keeps the in-memory state across restarts by saving a snapshot to a database.

The domain objects stay in memory, as before. After every request that changes something, a background
thread saves a snapshot of the stores (lectures, recordings, homework, notes, devices, passwords and PINs).
When the server starts, the last snapshot is loaded back into the same objects.

Large binary values (recordings, uploaded files) are saved once as separate blobs, addressed by their
SHA-256, so a new snapshot does not upload them again. Firestore limits a document to 1 MB, so every value
is split into parts.

Without FIREBASE_CREDENTIALS (for example on a developer machine or in the tests) nothing is saved and the
server works in memory only.
"""
from __future__ import annotations

import atexit
import hashlib
import io
import json
import logging
import os
import pickle
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("course_hub.persistence")


def _say(message: str) -> None:
    """One clear line in the server log (Render shows stdout), easy to find with the word 'state'."""
    print(f"[state] {message}", flush=True)

BLOB_MIN_BYTES = 64 * 1024          # bytes values at least this big are saved once, as blobs
PART_BYTES = 900 * 1024              # below the 1 MB document limit of Firestore
SAVE_DELAY_SECONDS = 2.0             # wait a moment so a burst of changes is saved once
INIT_ERROR = [""]                    # why Firestore could not be used, shown on /api/state-status
_LOCK_TYPES = (type(threading.Lock()), type(threading.RLock()))


class Backend:
    """Where snapshots and blobs are kept."""
    name = "none"

    def get_main(self) -> Optional[bytes]: raise NotImplementedError
    def put_main(self, data: bytes) -> None: raise NotImplementedError
    def has_blob(self, key: str) -> bool: raise NotImplementedError
    def put_blob(self, key: str, data: bytes) -> None: raise NotImplementedError
    def get_blob(self, key: str) -> bytes: raise NotImplementedError


class MemoryBackend(Backend):
    """For the tests: behaves like the database, inside one process."""
    name = "memory"

    def __init__(self):
        self.main: Optional[bytes] = None
        self.blobs: dict[str, bytes] = {}

    def get_main(self): return self.main
    def put_main(self, data): self.main = data
    def has_blob(self, key): return key in self.blobs
    def put_blob(self, key, data): self.blobs[key] = data
    def get_blob(self, key): return self.blobs[key]


def _parts(data: bytes) -> list[bytes]:
    return [data[i:i + PART_BYTES] for i in range(0, len(data), PART_BYTES)] or [b""]


class FirestoreBackend(Backend):
    """Cloud Firestore (Firebase, free Spark plan). One collection; values are split into parts."""
    name = "firestore"

    def __init__(self, credentials_json: str, collection: str = "course_hub"):
        import firebase_admin                      # imported here so the tests do not need the package
        from firebase_admin import credentials, firestore
        info = json.loads(credentials_json)
        app = firebase_admin.initialize_app(credentials.Certificate(info), name="course-hub-state")
        self._col = firestore.client(app).collection(collection)

    def _write_parts(self, prefix: str, data: bytes) -> int:
        chunks = _parts(data)
        for i, chunk in enumerate(chunks):
            self._col.document(f"{prefix}_{i}").set({"data": chunk})
        return len(chunks)

    def _read_parts(self, prefix: str, count: int) -> bytes:
        return b"".join(self._col.document(f"{prefix}_{i}").get().to_dict()["data"] for i in range(count))

    def get_main(self):
        meta = self._col.document("main").get()
        if not meta.exists:
            return None
        info = meta.to_dict()
        return self._read_parts(f"main_{info['gen']}", info["parts"])

    def put_main(self, data):
        old = self._col.document("main").get()
        gen = time.time_ns()
        parts = self._write_parts(f"main_{gen}", data)
        self._col.document("main").set({"gen": gen, "parts": parts, "saved_at": time.time()})   # switch only when complete
        if old.exists:
            info = old.to_dict()
            for i in range(info["parts"]):
                self._col.document(f"main_{info['gen']}_{i}").delete()

    def has_blob(self, key):
        return self._col.document(f"blob_{key}").get().exists

    def put_blob(self, key, data):
        parts = self._write_parts(f"blob_{key}", data)
        self._col.document(f"blob_{key}").set({"parts": parts, "size": len(data)})

    def get_blob(self, key):
        info = self._col.document(f"blob_{key}").get().to_dict()
        return self._read_parts(f"blob_{key}", info["parts"])


class _Pickler(pickle.Pickler):
    def __init__(self, file, store_blob: Callable[[bytes], str]):
        super().__init__(file, protocol=pickle.HIGHEST_PROTOCOL)
        self._store_blob = store_blob

    def persistent_id(self, obj):
        if isinstance(obj, bytes) and len(obj) >= BLOB_MIN_BYTES:
            return "blob:" + self._store_blob(obj)
        return None

    def reducer_override(self, obj):
        if isinstance(obj, _LOCK_TYPES):           # locks cannot be saved; a fresh one is created on load
            return (threading.RLock if "RLock" in type(obj).__name__ else threading.Lock), ()
        return NotImplemented


class _Unpickler(pickle.Unpickler):
    def __init__(self, file, load_blob: Callable[[str], bytes]):
        super().__init__(file)
        self._load_blob = load_blob

    def persistent_load(self, pid):
        if isinstance(pid, str) and pid.startswith("blob:"):
            return self._load_blob(pid[5:])
        raise pickle.UnpicklingError("unknown reference")


class StatePersistence:
    """Saves and loads a set of named objects. Loading copies the saved fields into the existing objects."""

    def __init__(self, backend: Optional[Backend], objects: dict[str, object]):
        self.backend = backend
        self.objects = objects
        self._known_blobs: set[str] = set()
        self._dirty = threading.Event()
        self._save_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._pid = 0
        self.saves = 0
        self.saving_since = 0.0
        self.last_error = ""
        self.last_saved_at = 0.0

    @property
    def enabled(self) -> bool:
        return self.backend is not None

    # ---- snapshot ------------------------------------------------------------------
    def _store_blob(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        if key not in self._known_blobs:
            if not self.backend.has_blob(key):
                self.backend.put_blob(key, data)
            self._known_blobs.add(key)
        return key

    def dump(self) -> bytes:
        for attempt in range(5):
            try:
                buffer = io.BytesIO()
                _Pickler(buffer, self._store_blob).dump({k: v.__dict__ for k, v in self.objects.items()})
                return buffer.getvalue()
            except RuntimeError:                     # a dict changed while it was being read; try again
                time.sleep(0.05 * (attempt + 1))
        raise RuntimeError("state kept changing while saving")

    def save_now(self) -> bool:
        if not self.enabled:
            return False
        with self._save_lock:
            try:
                self.backend.put_main(self.dump())
                if not self.last_saved_at:
                    _say(f"first snapshot saved to {self.backend.name}")
                self.last_saved_at, self.last_error = time.time(), ""
                self.saves += 1
                return True
            except Exception as exc:                 # never break a request because the database failed
                self.last_error = f"{type(exc).__name__}: {exc}"
                _say(f"saving FAILED: {self.last_error}")
                return False

    def load(self) -> bool:
        if not self.enabled:
            return False
        try:
            data = self.backend.get_main()
            if not data:
                _say(f"connected to {self.backend.name}; no saved state yet")
                return False
            saved = _Unpickler(io.BytesIO(data), self._load_blob).load()
            for name, fields in saved.items():
                if name in self.objects:
                    self.objects[name].__dict__.update(fields)
            _say(f"loaded the saved state from {self.backend.name}")
            return True
        except Exception as exc:                     # a damaged snapshot must not stop the server
            self.last_error = f"{type(exc).__name__}: {exc}"
            _say(f"loading FAILED: {self.last_error}")
            return False

    def _load_blob(self, key: str) -> bytes:
        self._known_blobs.add(key)
        return self.backend.get_blob(key)

    # ---- background saving ------------------------------------------------------------
    def mark_dirty(self) -> None:
        if self.enabled:
            self._dirty.set()
            self.start()          # make sure the saver runs in this process (a pre-forking server copies no threads)

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread is not None and self._thread.is_alive() and self._pid == os.getpid():
            return
        self._pid = os.getpid()
        self._thread = threading.Thread(target=self._loop, name="state-saver", daemon=True)
        self._thread.start()
        atexit.register(self._save_if_dirty)    # a deployment stops the old server; keep its last changes

    def _save_if_dirty(self) -> None:
        if self._dirty.is_set():
            self._dirty.clear()
            self.save_now()

    def _loop(self) -> None:
        while True:
            try:
                self._dirty.wait()
                time.sleep(SAVE_DELAY_SECONDS)
                self._dirty.clear()
                self.saving_since = time.time()
                self.save_now()
                self.saving_since = 0.0
            except Exception as exc:            # keep the saver alive whatever happens
                self.last_error = f"{type(exc).__name__}: {exc}"


def build_backend(credentials_json: str) -> Optional[Backend]:
    """Firestore when credentials are configured; otherwise None (memory only)."""
    if not credentials_json.strip():
        _say("FIREBASE_CREDENTIALS is not set; memory only")
        return None
    try:
        return FirestoreBackend(credentials_json)
    except Exception as exc:
        INIT_ERROR[0] = f"{type(exc).__name__}: {exc}"
        _say(f"Firestore is not available ({INIT_ERROR[0]}); memory only")
        return None


def status(persistence: "StatePersistence") -> dict:
    """What the lecturer sees on /api/state-status."""
    return {"enabled": persistence.enabled, "backend": persistence.backend.name if persistence.backend else "none",
            "last_saved_at": persistence.last_saved_at, "last_error": persistence.last_error,
            "init_error": INIT_ERROR[0], "saves": persistence.saves, "pending": persistence._dirty.is_set(),
            "saving_for_seconds": round(time.time() - persistence.saving_since) if persistence.saving_since else 0,
            "saver_running": bool(persistence._thread and persistence._thread.is_alive() and persistence._pid == os.getpid())}

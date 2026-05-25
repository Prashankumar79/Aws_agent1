"""
job_store.py — Thread-safe persistent job store backed by a JSON file.

Replaces the plain `_jobs: dict = {}` in jobs.py and `_rag_jobs: dict = {}`
in rag.py.  Jobs survive uvicorn --reload and server restarts.

Design notes:
  * The top-level store is a `JobStore` (subclass of `dict`) keyed by job_id.
  * Each job value is wrapped in a `_PersistentJob` proxy that persists on every
    nested __setitem__ — fixes the data-loss bug where `job["graph_json"] = x`
    after the initial `_jobs[job_id] = {...}` was never written to disk.
  * Writes are atomic (tmp file + rename).
  * A single global RLock guards both read and write to avoid torn reads.
"""

# 🟢 BEGINNER: Standard-library imports for JSON, logging, threading and typing.
import json
import logging
import threading
from pathlib import Path
from typing import Any, Iterator

# 🟢 BEGINNER: Logger for this module. Messages appear with [JobStore] prefix.
logger = logging.getLogger(__name__)

# 🟢 BEGINNER: Where the JSON files live. One file per "namespace" (e.g. pipeline.json, rag.json).
_STORE_DIR = Path("storage/job_store")
# 🟢 BEGINNER: An RLock lets the SAME thread acquire the lock multiple times
# (regular Lock would deadlock when a method that holds the lock calls another method that needs it).
_LOCK = threading.RLock()


def _path(namespace: str) -> Path:
    """🟢 BEGINNER: Build the on-disk path for a given namespace, creating the folder if needed."""
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORE_DIR / f"{namespace}.json"


def _load(namespace: str) -> dict:
    """🟢 BEGINNER: Read the JSON file for a namespace. Returns {} on first run or corruption."""
    p = _path(namespace)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning(f"[JobStore] {p} is not a JSON object — starting empty")
                return {}
            logger.info(f"[JobStore] Loaded {len(data)} jobs from {p}")
            return data
        except Exception as e:
            logger.warning(f"[JobStore] Could not read {p}: {e} — starting empty")
    return {}


def _flush(namespace: str, store: dict) -> None:
    """🟢 BEGINNER: Atomically write the store to disk.

    We write to a `.tmp` file first, then rename it on top of the real file.
    This way, even if the server is killed mid-write, the real file is either
    the old version OR the new version — never half-written garbage.
    """
    try:
        p = _path(namespace)
        tmp = p.with_suffix(".tmp")
        # 🟢 BEGINNER: Convert any _PersistentJob values back to plain dicts for JSON serialisation.
        serialisable = {k: dict(v) if isinstance(v, _PersistentJob) else v for k, v in store.items()}
        tmp.write_text(json.dumps(serialisable, default=str), encoding="utf-8")
        tmp.replace(p)
    except Exception as e:
        logger.warning(f"[JobStore] Flush failed for {namespace}: {e}")


# 🟢 BEGINNER: This wrapper class is the heart of the data-loss fix.
# A regular Python dict has no idea it's stored inside another dict, so when
# you write `_jobs[id]["graph_json"] = x`, the OUTER JobStore is never told.
# _PersistentJob keeps a back-pointer to the JobStore and triggers a flush on every write.
class _PersistentJob(dict):
    """A dict that triggers a flush on the parent JobStore whenever it mutates.

    This is what fixes the data-loss bug: ``job["graph_json"] = ...`` now
    persists immediately instead of only living in memory.
    """

    __slots__ = ("_store",)

    def __init__(self, data: dict, store: "JobStore"):
        super().__init__(data)
        self._store = store

    # 🟢 BEGINNER: All mutating dict methods go through one of the overrides below.
    def __setitem__(self, key: str, value: Any) -> None:
        with self._store._lock:
            super().__setitem__(key, value)
            self._store._flush()

    def __delitem__(self, key: str) -> None:
        with self._store._lock:
            super().__delitem__(key)
            self._store._flush()

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        with self._store._lock:
            super().update(*args, **kwargs)
            self._store._flush()

    def setdefault(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        with self._store._lock:
            existed = key in self
            value = super().setdefault(key, default)
            if not existed:
                self._store._flush()
            return value

    def pop(self, key: str, *args: Any) -> Any:  # type: ignore[override]
        with self._store._lock:
            value = super().pop(key, *args)
            self._store._flush()
            return value

    def clear(self) -> None:  # type: ignore[override]
        with self._store._lock:
            super().clear()
            self._store._flush()


# 🟢 BEGINNER: The top-level container. Same API as a regular dict, but every
# write is persisted to disk and every job dict inside is auto-wrapped.
class JobStore(dict):
    """A dict subclass that persists every write to disk (JSON).

    Drop-in replacement for plain ``_jobs = {}``. Both top-level and nested
    writes (``_jobs[id]["graph_json"] = ...``) are persisted.
    """

    def __init__(self, namespace: str):
        self._namespace = namespace
        self._lock = _LOCK
        data = _load(namespace)
        # 🟢 BEGINNER: Jobs that were mid-flight when the server died can never
        # finish — mark them failed so the frontend stops polling forever.
        # We catch THREE cases:
        #   1. status is running/indexing  (vision pipeline mid-flight)
        #   2. stage ends in _GENERATING   (design doc / terraform mid-flight)
        #   3. stage is graph_ready but no design_docs    (SSE stream was alive)
        # All three are "doomed" states the user can only escape via re-submit.
        _DOOMED_STATUS = {"running", "indexing"}
        _DOOMED_STAGE_SUFFIX = "_GENERATING"
        for job in data.values():
            if not isinstance(job, dict):
                continue
            stage = str(job.get("pipeline_stage", ""))
            status = job.get("status")
            stale = (
                status in _DOOMED_STATUS
                or stage.endswith(_DOOMED_STAGE_SUFFIX)
                or (status == "graph_ready" and not job.get("design_docs"))
            )
            if stale and status != "failed":
                job["status"] = "failed"
                job["error_message"] = (
                    job.get("error_message")
                    or "Server restarted while job was mid-flight. Please re-submit."
                )
                job["pipeline_stage"] = "FAILED"
        # 🟢 BEGINNER: Wrap every job dict in a _PersistentJob so nested writes flush automatically.
        wrapped = {k: _PersistentJob(v if isinstance(v, dict) else {"value": v}, self) for k, v in data.items()}
        super().__init__(wrapped)
        if data:
            self._flush()

    def _flush(self) -> None:
        """🟢 BEGINNER: Internal helper — snapshot current state and write to disk."""
        _flush(self._namespace, dict(self))

    # ── Mutating overrides ──────────────────────────────────────────────
    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            # 🟢 BEGINNER: Always wrap dict values so nested writes persist.
            if isinstance(value, dict) and not isinstance(value, _PersistentJob):
                value = _PersistentJob(value, self)
            super().__setitem__(key, value)
            self._flush()

    def __delitem__(self, key: str) -> None:
        with self._lock:
            super().__delitem__(key)
            self._flush()

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        with self._lock:
            super().update(*args, **kwargs)
            # 🟢 BEGINNER: Re-wrap any plain dicts that slipped in via update().
            for k, v in list(self.items()):
                if isinstance(v, dict) and not isinstance(v, _PersistentJob):
                    super().__setitem__(k, _PersistentJob(v, self))
            self._flush()

    def pop(self, key: str, *args: Any) -> Any:  # type: ignore[override]
        with self._lock:
            value = super().pop(key, *args)
            self._flush()
            return value

    def clear(self) -> None:  # type: ignore[override]
        with self._lock:
            super().clear()
            self._flush()

    # ── Read overrides for thread-safety ────────────────────────────────
    # 🟢 BEGINNER: Reads also go through the lock so we never observe a half-written state
    # while a background thread is updating the same job.
    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        with self._lock:
            return super().get(key, default)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(list(super().keys()))

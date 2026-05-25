"""Tests for app.core.job_store — the persistent dict that survives restarts."""

# 🟢 BEGINNER: These tests are critical because they cover the data-loss bug fix:
# nested writes (job["graph_json"] = x) MUST be persisted to disk.
import json
from pathlib import Path

from app.core.job_store import JobStore


def test_top_level_write_persists():
    # 🟢 BEGINNER: Writing a fresh job should immediately hit disk.
    store = JobStore("test_top")
    store["job1"] = {"status": "running", "x": 1}

    on_disk = json.loads(Path("storage/job_store/test_top.json").read_text())
    assert on_disk["job1"]["status"] == "running"


def test_nested_write_persists():
    """🟢 BEGINNER: This is THE regression test for the data-loss bug.

    Before the fix, ``store["job1"]["graph_json"] = "x"`` only mutated the
    in-memory dict — the JSON file never got the update. After the fix, the
    inner dict is wrapped in _PersistentJob and triggers a flush.
    """
    store = JobStore("test_nested")
    store["job1"] = {"status": "running"}
    store["job1"]["graph_json"] = "important-data"

    on_disk = json.loads(Path("storage/job_store/test_nested.json").read_text())
    assert on_disk["job1"]["graph_json"] == "important-data"


def test_running_jobs_are_marked_failed_on_restart():
    # 🟢 BEGINNER: When the server crashes mid-pipeline, those jobs can never finish.
    # On restart we mark them failed so the UI doesn't poll forever.
    s1 = JobStore("test_restart")
    s1["alive"] = {"status": "complete"}
    s1["zombie"] = {"status": "running"}

    s2 = JobStore("test_restart")  # simulate restart
    assert s2["alive"]["status"] == "complete"
    assert s2["zombie"]["status"] == "failed"
    assert "Server restarted" in s2["zombie"]["error_message"]


def test_atomic_write_uses_tmp_file():
    # 🟢 BEGINNER: tmp + rename means a kill -9 mid-write never corrupts the file.
    store = JobStore("test_atomic")
    store["j"] = {"status": "running"}
    # The .tmp file should not be left behind after a successful flush.
    assert not Path("storage/job_store/test_atomic.tmp").exists()
    assert Path("storage/job_store/test_atomic.json").exists()


def test_delete_persists():
    store = JobStore("test_delete")
    store["job1"] = {"status": "running"}
    del store["job1"]
    on_disk = json.loads(Path("storage/job_store/test_delete.json").read_text())
    assert "job1" not in on_disk

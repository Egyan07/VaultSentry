# =============================================================================
#   tests/test_snapshots.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Tests for snapshot functions in core/database.py
# =============================================================================

import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


def _seed_files(db_path, records):
    """Insert file_hashes records."""
    conn = sqlite3.connect(db_path)
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for filepath, sha256, size, status in records:
        conn.execute(
            "INSERT OR REPLACE INTO file_hashes "
            "(filepath, sha256, file_size, entropy, first_seen, last_verified, last_modified, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (filepath, sha256, size, 5.0, now, now, now, status)
        )
    conn.commit()
    conn.close()


# =============================================================================
#   create_snapshot
# =============================================================================

class TestCreateSnapshot:
    def test_returns_positive_id(self, db_env):
        _seed_files(db_env["db_path"], [
            ("/backup/a.zip", "aaa", 100, "OK"),
        ])
        from core.database import create_snapshot
        snap_id = create_snapshot("test snapshot")
        assert snap_id > 0

    def test_snapshot_row_created(self, db_env):
        _seed_files(db_env["db_path"], [
            ("/backup/a.zip", "aaa", 100, "OK"),
        ])
        from core.database import create_snapshot
        snap_id = create_snapshot("my label", "my notes")

        conn = sqlite3.connect(db_env["db_path"])
        row  = conn.execute(
            "SELECT label, notes, file_count FROM snapshots WHERE id=?",
            (snap_id,)
        ).fetchone()
        conn.close()
        assert row[0] == "my label"
        assert row[1] == "my notes"
        assert row[2] == 1

    def test_snapshot_files_copied(self, db_env):
        _seed_files(db_env["db_path"], [
            ("/backup/a.zip", "aaa", 100, "OK"),
            ("/backup/b.bak", "bbb", 200, "CHANGED"),
        ])
        from core.database import create_snapshot
        snap_id = create_snapshot("two files")

        conn = sqlite3.connect(db_env["db_path"])
        count = conn.execute(
            "SELECT COUNT(*) FROM snapshot_files WHERE snapshot_id=?",
            (snap_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 2

    def test_returns_minus_one_when_no_db(self, tmp_path, monkeypatch):
        import core.database as db_mod
        monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "nonexistent.db"))
        from core.database import create_snapshot
        assert create_snapshot("label") == -1

    def test_empty_baseline_gives_zero_files(self, db_env):
        from core.database import create_snapshot
        snap_id = create_snapshot("empty")
        assert snap_id > 0

        conn = sqlite3.connect(db_env["db_path"])
        count = conn.execute(
            "SELECT file_count FROM snapshots WHERE id=?", (snap_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_multiple_snapshots_are_independent(self, db_env):
        """Two snapshots of the same baseline must each have their own records."""
        _seed_files(db_env["db_path"], [
            ("/backup/a.zip", "aaa", 100, "OK"),
        ])
        from core.database import create_snapshot
        snap1 = create_snapshot("snap1")
        snap2 = create_snapshot("snap2")

        conn = sqlite3.connect(db_env["db_path"])
        c1 = conn.execute(
            "SELECT COUNT(*) FROM snapshot_files WHERE snapshot_id=?", (snap1,)
        ).fetchone()[0]
        c2 = conn.execute(
            "SELECT COUNT(*) FROM snapshot_files WHERE snapshot_id=?", (snap2,)
        ).fetchone()[0]
        conn.close()
        assert c1 == 1 and c2 == 1
        assert snap1 != snap2


# =============================================================================
#   list_snapshots
# =============================================================================

class TestListSnapshots:
    def test_returns_empty_when_none(self, db_env):
        from core.database import list_snapshots
        assert list_snapshots() == []

    def test_returns_most_recent_first(self, db_env):
        from core.database import create_snapshot, list_snapshots
        create_snapshot("first")
        create_snapshot("second")
        snaps = list_snapshots()
        assert snaps[0]["label"] == "second"
        assert snaps[1]["label"] == "first"

    def test_returns_correct_fields(self, db_env):
        from core.database import create_snapshot, list_snapshots
        create_snapshot("labelled", "some notes")
        snaps = list_snapshots()
        assert "id"         in snaps[0]
        assert "label"      in snaps[0]
        assert "created_at" in snaps[0]
        assert "file_count" in snaps[0]
        assert "notes"      in snaps[0]
        assert snaps[0]["label"] == "labelled"
        assert snaps[0]["notes"] == "some notes"


# =============================================================================
#   get_snapshot_files
# =============================================================================

class TestGetSnapshotFiles:
    def test_returns_files_for_snapshot(self, db_env):
        _seed_files(db_env["db_path"], [
            ("/backup/a.zip", "aaa", 100, "OK"),
            ("/backup/b.zip", "bbb", 200, "CHANGED"),
        ])
        from core.database import create_snapshot, get_snapshot_files
        snap_id = create_snapshot("test")
        files = get_snapshot_files(snap_id)
        assert len(files) == 2

    def test_returns_empty_for_unknown_id(self, db_env):
        from core.database import get_snapshot_files
        assert get_snapshot_files(99999) == []

    def test_file_fields_correct(self, db_env):
        _seed_files(db_env["db_path"], [
            ("/backup/data.zip", "abc123", 512, "OK"),
        ])
        from core.database import create_snapshot, get_snapshot_files
        snap_id = create_snapshot("fields test")
        files = get_snapshot_files(snap_id)
        assert files[0]["filepath"]  == "/backup/data.zip"
        assert files[0]["sha256"]    == "abc123"
        assert files[0]["file_size"] == 512
        assert files[0]["status"]    == "OK"


# =============================================================================
#   diff_snapshots
# =============================================================================

class TestDiffSnapshots:
    def test_detects_added_file(self, db_env):
        _seed_files(db_env["db_path"], [("/backup/a.zip", "aaa", 100, "OK")])
        from core.database import create_snapshot, diff_snapshots
        snap_a = create_snapshot("before")

        _seed_files(db_env["db_path"], [("/backup/b.zip", "bbb", 200, "NEW")])
        snap_b = create_snapshot("after")

        diff = diff_snapshots(snap_a, snap_b)
        added_paths = [f["filepath"] for f in diff["added"]]
        assert "/backup/b.zip" in added_paths

    def test_detects_removed_file(self, db_env):
        _seed_files(db_env["db_path"], [
            ("/backup/a.zip", "aaa", 100, "OK"),
            ("/backup/b.zip", "bbb", 200, "OK"),
        ])
        from core.database import create_snapshot, diff_snapshots
        import sqlite3
        snap_a = create_snapshot("before")

        # Remove b.zip from baseline
        conn = sqlite3.connect(db_env["db_path"])
        conn.execute("DELETE FROM file_hashes WHERE filepath='/backup/b.zip'")
        conn.commit()
        conn.close()

        snap_b = create_snapshot("after")
        diff   = diff_snapshots(snap_a, snap_b)
        removed_paths = [f["filepath"] for f in diff["removed"]]
        assert "/backup/b.zip" in removed_paths

    def test_detects_changed_file(self, db_env):
        _seed_files(db_env["db_path"], [("/backup/a.zip", "hash_v1", 100, "OK")])
        from core.database import create_snapshot, diff_snapshots
        import sqlite3
        snap_a = create_snapshot("before")

        # Update hash in baseline
        conn = sqlite3.connect(db_env["db_path"])
        conn.execute(
            "UPDATE file_hashes SET sha256='hash_v2' WHERE filepath='/backup/a.zip'"
        )
        conn.commit()
        conn.close()

        snap_b = create_snapshot("after")
        diff   = diff_snapshots(snap_a, snap_b)
        assert len(diff["changed"]) == 1
        assert diff["changed"][0]["filepath"]  == "/backup/a.zip"
        assert diff["changed"][0]["sha256_a"] == "hash_v1"
        assert diff["changed"][0]["sha256_b"] == "hash_v2"

    def test_unchanged_files_counted(self, db_env):
        _seed_files(db_env["db_path"], [("/backup/a.zip", "same_hash", 100, "OK")])
        from core.database import create_snapshot, diff_snapshots
        snap_a = create_snapshot("before")
        snap_b = create_snapshot("after")  # nothing changed

        diff = diff_snapshots(snap_a, snap_b)
        assert len(diff["unchanged"]) == 1
        assert len(diff["added"])     == 0
        assert len(diff["removed"])   == 0
        assert len(diff["changed"])   == 0

    def test_empty_snapshots_diff_empty(self, db_env):
        from core.database import create_snapshot, diff_snapshots
        snap_a = create_snapshot("empty_a")
        snap_b = create_snapshot("empty_b")
        diff   = diff_snapshots(snap_a, snap_b)
        assert diff == {"added": [], "removed": [], "changed": [], "unchanged": []}


# =============================================================================
#   delete_snapshot
# =============================================================================

class TestDeleteSnapshot:
    def test_deletes_snapshot_and_files(self, db_env):
        _seed_files(db_env["db_path"], [("/backup/a.zip", "aaa", 100, "OK")])
        from core.database import create_snapshot, delete_snapshot, list_snapshots
        snap_id = create_snapshot("to delete")

        result = delete_snapshot(snap_id)
        assert result is True

        snaps = list_snapshots()
        assert all(s["id"] != snap_id for s in snaps)

        conn = sqlite3.connect(db_env["db_path"])
        count = conn.execute(
            "SELECT COUNT(*) FROM snapshot_files WHERE snapshot_id=?", (snap_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_delete_nonexistent_returns_true(self, db_env):
        from core.database import delete_snapshot
        # SQLite DELETE of non-existent row succeeds silently
        assert delete_snapshot(99999) is True

    def test_other_snapshots_unaffected(self, db_env):
        _seed_files(db_env["db_path"], [("/backup/a.zip", "aaa", 100, "OK")])
        from core.database import create_snapshot, delete_snapshot, list_snapshots
        snap_keep   = create_snapshot("keep")
        snap_delete = create_snapshot("delete me")

        delete_snapshot(snap_delete)
        snaps = list_snapshots()
        assert any(s["id"] == snap_keep for s in snaps)
        assert all(s["id"] != snap_delete for s in snaps)

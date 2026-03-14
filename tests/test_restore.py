# =============================================================================
#   tests/test_restore.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Tests for core/restore.py
#   Uses tmp_path — no real files modified.
# =============================================================================

import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch

from core.restore import (
    get_restorable_files, plan_restore, execute_restore,
    RestoreItem, RestorePlan, _relative_to_backup_root,
)


# =============================================================================
#   Helpers
# =============================================================================

def _seed_db(db_path, records):
    """Insert file_hashes records for testing."""
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
#   _relative_to_backup_root
# =============================================================================

class TestRelativeToBackupRoot:
    def test_strips_backup_root(self, tmp_path, monkeypatch):
        root = str(tmp_path / "backups")
        filepath = os.path.join(root, "clientA", "data.zip")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [root])

        rel = _relative_to_backup_root(filepath)
        assert rel == os.path.join("clientA", "data.zip")

    def test_longest_match_wins(self, tmp_path, monkeypatch):
        root1 = str(tmp_path / "backups")
        root2 = str(tmp_path / "backups" / "sub")
        filepath = os.path.join(root2, "data.zip")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [root1, root2])

        rel = _relative_to_backup_root(filepath)
        assert rel == "data.zip"  # stripped the longer root2

    def test_fallback_to_filename_when_no_match(self, tmp_path, monkeypatch):
        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(tmp_path / "other")])

        rel = _relative_to_backup_root("/completely/different/path/file.zip")
        assert rel == "file.zip"


# =============================================================================
#   get_restorable_files
# =============================================================================

class TestGetRestorableFiles:
    def test_returns_all_files_no_filter(self, db_env):
        records = [
            (str(db_env["backup_dir"] / "a.zip"), "aaa", 100, "OK"),
            (str(db_env["backup_dir"] / "b.zip"), "bbb", 200, "CHANGED"),
            (str(db_env["backup_dir"] / "c.zip"), "ccc", 300, "MISSING"),
        ]
        _seed_db(db_env["db_path"], records)

        items = get_restorable_files(status_filter=None)
        assert len(items) == 3

    def test_filter_by_changed(self, db_env):
        records = [
            (str(db_env["backup_dir"] / "a.zip"), "aaa", 100, "OK"),
            (str(db_env["backup_dir"] / "b.zip"), "bbb", 200, "CHANGED"),
        ]
        _seed_db(db_env["db_path"], records)

        items = get_restorable_files(status_filter=["CHANGED"])
        assert len(items) == 1
        assert items[0].status == "CHANGED"

    def test_filter_multiple_statuses(self, db_env):
        records = [
            (str(db_env["backup_dir"] / "a.zip"), "aaa", 100, "OK"),
            (str(db_env["backup_dir"] / "b.zip"), "bbb", 200, "CHANGED"),
            (str(db_env["backup_dir"] / "c.zip"), "ccc", 300, "MISSING"),
        ]
        _seed_db(db_env["db_path"], records)

        items = get_restorable_files(status_filter=["CHANGED", "MISSING"])
        assert len(items) == 2
        statuses = {i.status for i in items}
        assert statuses == {"CHANGED", "MISSING"}

    def test_returns_empty_when_no_db(self, tmp_path, monkeypatch):
        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "DB_PATH", str(tmp_path / "nonexistent.db"))
        items = get_restorable_files()
        assert items == []

    def test_returns_empty_when_no_matching_records(self, db_env):
        records = [
            (str(db_env["backup_dir"] / "a.zip"), "aaa", 100, "OK"),
        ]
        _seed_db(db_env["db_path"], records)

        items = get_restorable_files(status_filter=["MISSING"])
        assert items == []


# =============================================================================
#   plan_restore
# =============================================================================

class TestPlanRestore:
    def test_builds_dest_paths(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()

        f = backup_dir / "subdir" / "data.zip"
        f.parent.mkdir()
        f.write_bytes(b"PK")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(f), sha256="abc", file_size=2, status="CHANGED")]
        plan  = plan_restore(items, str(dest_dir))

        assert len(plan.items) == 1
        expected = os.path.join(str(dest_dir), "subdir", "data.zip")
        assert plan.items[0].dest_path == expected

    def test_detects_conflict(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src  = backup_dir / "data.zip"
        src.write_bytes(b"PK")
        dest = dest_dir / "data.zip"
        dest.write_bytes(b"existing")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc", file_size=2, status="CHANGED")]
        plan  = plan_restore(items, str(dest_dir))

        assert plan.already_exist == 1
        assert plan.items[0].exists_at_dest is True

    def test_detects_missing_source(self, tmp_path, monkeypatch):
        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(tmp_path)])

        items = [RestoreItem(filepath="/no/such/file.zip",
                             sha256="abc", file_size=100, status="MISSING")]
        plan  = plan_restore(items, str(tmp_path / "restore"))

        assert plan.missing_src == 1

    def test_sums_total_size(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [
            RestoreItem(filepath=str(backup_dir / "a.zip"), sha256="a", file_size=1000, status="OK"),
            RestoreItem(filepath=str(backup_dir / "b.zip"), sha256="b", file_size=2000, status="OK"),
        ]
        plan = plan_restore(items, str(tmp_path / "restore"))
        assert plan.total_size == 3000


# =============================================================================
#   execute_restore
# =============================================================================

class TestExecuteRestore:
    def test_copies_file_to_destination(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src = backup_dir / "data.zip"
        src.write_bytes(b"backup content")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc",
                             file_size=14, status="CHANGED")]
        plan  = plan_restore(items, str(dest_dir))
        result = execute_restore(plan)

        assert result.restored == 1
        assert result.failed   == 0
        dest_file = dest_dir / "data.zip"
        assert dest_file.exists()
        assert dest_file.read_bytes() == b"backup content"

    def test_skips_missing_source(self, tmp_path, monkeypatch):
        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(tmp_path)])

        items = [RestoreItem(filepath="/no/such/file.zip",
                             sha256="abc", file_size=100, status="MISSING",
                             dest_path=str(tmp_path / "restore" / "file.zip"),
                             exists_at_dest=False)]
        plan  = RestorePlan(destination=str(tmp_path / "restore"), items=items)
        result = execute_restore(plan)

        assert result.failed == 1
        assert result.restored == 0
        assert len(result.errors) == 1

    def test_skips_existing_when_skip_flag(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src  = backup_dir / "data.zip"
        dest = dest_dir   / "data.zip"
        src.write_bytes(b"new content")
        dest.write_bytes(b"existing")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc",
                             file_size=11, status="CHANGED")]
        plan  = plan_restore(items, str(dest_dir))
        result = execute_restore(plan, skip_existing=True)

        assert result.skipped  == 1
        assert result.restored == 0
        assert dest.read_bytes() == b"existing"  # unchanged

    def test_overwrites_when_overwrite_all(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src  = backup_dir / "data.zip"
        dest = dest_dir   / "data.zip"
        src.write_bytes(b"new content")
        dest.write_bytes(b"old content")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc",
                             file_size=11, status="CHANGED")]
        plan  = plan_restore(items, str(dest_dir))
        result = execute_restore(plan, overwrite_all=True)

        assert result.restored == 1
        assert dest.read_bytes() == b"new content"

    def test_overwrite_set_only_overwrites_approved(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src_a = backup_dir / "a.zip"
        src_b = backup_dir / "b.zip"
        dest_a = dest_dir / "a.zip"
        dest_b = dest_dir / "b.zip"
        src_a.write_bytes(b"new A")
        src_b.write_bytes(b"new B")
        dest_a.write_bytes(b"old A")
        dest_b.write_bytes(b"old B")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [
            RestoreItem(filepath=str(src_a), sha256="a", file_size=5, status="CHANGED"),
            RestoreItem(filepath=str(src_b), sha256="b", file_size=5, status="CHANGED"),
        ]
        plan = plan_restore(items, str(dest_dir))

        # Only approve overwrite of a.zip
        result = execute_restore(plan, overwrite_set={str(dest_a)})

        assert result.restored == 1
        assert result.skipped  == 1
        assert dest_a.read_bytes() == b"new A"   # overwritten
        assert dest_b.read_bytes() == b"old B"   # not touched

    def test_creates_subdirectory_structure(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()

        src = backup_dir / "clientA" / "2026" / "data.zip"
        src.parent.mkdir(parents=True)
        src.write_bytes(b"data")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc",
                             file_size=4, status="CHANGED")]
        plan  = plan_restore(items, str(dest_dir))
        result = execute_restore(plan)

        assert result.restored == 1
        restored_file = dest_dir / "clientA" / "2026" / "data.zip"
        assert restored_file.exists()

    def test_progress_callback_called(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src = backup_dir / "f.zip"
        src.write_bytes(b"data")

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc",
                             file_size=4, status="OK")]
        plan  = plan_restore(items, str(dest_dir))

        calls = []
        execute_restore(plan, progress_callback=lambda c, t, f: calls.append((c, t)))
        assert len(calls) == 1
        assert calls[0] == (1, 1)

    def test_duration_is_positive(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        dest_dir   = tmp_path / "restore"
        backup_dir.mkdir()
        dest_dir.mkdir()

        src = backup_dir / "f.bak"
        src.write_bytes(b"x" * 1000)

        import core.restore as restore_mod
        monkeypatch.setattr(restore_mod, "BACKUP_PATHS", [str(backup_dir)])

        items = [RestoreItem(filepath=str(src), sha256="abc",
                             file_size=1000, status="OK")]
        plan   = plan_restore(items, str(dest_dir))
        result = execute_restore(plan)

        assert result.duration >= 0.0

# =============================================================================
#   tests/test_scanner.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import os
import sys
import sqlite3
import zipfile
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch


PATCH_ALERT = "core.scanner.raise_alert"


def _insert_record(db_path, filepath, sha256, entropy=5.0, size=1024, status="OK"):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO file_hashes "
        "(filepath, sha256, file_size, entropy, first_seen, last_verified, last_modified, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (filepath, sha256, size, entropy, now, now, now, status)
    )
    conn.commit()
    conn.close()


def _conn(db_path):
    return sqlite3.connect(db_path)


# =============================================================================
#   create_baseline
# =============================================================================

class TestCreateBaseline:
    def test_baselines_files_in_path(self, db_env):
        backup_dir = db_env["backup_dir"]
        (backup_dir / "data.zip").write_bytes(b"PK" + b"\x00" * 100)
        (backup_dir / "notes.bak").write_bytes(b"backup content")

        with patch(PATCH_ALERT):
            from core.scanner import create_baseline
            count = create_baseline()

        assert count == 2
        conn = sqlite3.connect(db_env["db_path"])
        assert conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0] == 2
        conn.close()

    def test_returns_zero_when_no_files(self, db_env):
        from core.scanner import create_baseline
        assert create_baseline() == 0

    def test_rerunning_updates_not_duplicates(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "data.zip"
        f.write_bytes(b"original")

        with patch(PATCH_ALERT):
            from core.scanner import create_baseline
            create_baseline()

        f.write_bytes(b"updated content")

        with patch(PATCH_ALERT):
            create_baseline()

        conn = sqlite3.connect(db_env["db_path"])
        assert conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0] == 1
        conn.close()

    def test_progress_callback_called_per_file(self, db_env):
        backup_dir = db_env["backup_dir"]
        (backup_dir / "a.zip").write_bytes(b"PK" + b"\x00" * 50)
        (backup_dir / "b.bak").write_bytes(b"backup")

        calls = []
        with patch(PATCH_ALERT):
            from core.scanner import create_baseline
            create_baseline(progress_callback=lambda c, t, p: calls.append((c, t)))

        assert len(calls) == 2
        assert calls[-1] == (2, 2)


# =============================================================================
#   _step_verify_baseline
# =============================================================================

class TestStepVerifyBaseline:
    def test_unchanged_file_is_ok(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "good.zip"
        f.write_bytes(b"PK" + b"\x00" * 100)
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        _insert_record(db_env["db_path"], str(f), sha)

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert:
            from core.scanner import _step_verify_baseline
            ok, changed, missing, alerts, _ = _step_verify_baseline(cur, now)

        conn.commit(); conn.close()
        assert ok == 1 and changed == 0 and missing == 0 and alerts == 0
        mock_alert.assert_not_called()

    def test_modified_file_triggers_alert(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "changed.bak"
        f.write_bytes(b"original content")
        _insert_record(db_env["db_path"], str(f), "deadbeef" * 8)

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False):
            from core.scanner import _step_verify_baseline
            ok, changed, missing, alerts, _ = _step_verify_baseline(cur, now)

        conn.commit(); conn.close()
        assert changed == 1 and alerts == 1
        mock_alert.assert_called_once()

    def test_missing_file_triggers_critical(self, db_env):
        _insert_record(db_env["db_path"], "/nonexistent/file.zip", "abc123")

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False):
            from core.scanner import _step_verify_baseline
            ok, changed, missing, alerts, _ = _step_verify_baseline(cur, now)

        conn.commit(); conn.close()
        assert missing == 1 and alerts == 1
        assert mock_alert.call_args[0][0] == "CRITICAL"

    def test_high_entropy_change_flagged_ransomware(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "encrypted.zip"
        f.write_bytes(bytes(range(256)) * 400)
        _insert_record(db_env["db_path"], str(f), "deadbeef" * 8, entropy=3.0)

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False), \
             patch("config.ENTROPY_SPIKE_THRESHOLD", 7.0):
            from core.scanner import _step_verify_baseline
            _step_verify_baseline(cur, now)

        conn.commit(); conn.close()
        assert mock_alert.called
        assert "RANSOMWARE" in mock_alert.call_args[0][1]


# =============================================================================
#   _step_detect_new_files
# =============================================================================

class TestStepDetectNewFiles:
    def test_new_file_added_to_db(self, db_env):
        backup_dir = db_env["backup_dir"]
        (backup_dir / "new.zip").write_bytes(b"PK" + b"\x00" * 50)

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT):
            from core.scanner import _step_detect_new_files
            count, alerts, _ = _step_detect_new_files(cur, now)

        conn.commit(); conn.close()
        assert count == 1 and alerts == 0

    def test_ransom_note_triggers_critical(self, db_env):
        backup_dir = db_env["backup_dir"]
        (backup_dir / "readme_decrypt.zip").write_bytes(b"PK" + b"\x00" * 50)

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False):
            from core.scanner import _step_detect_new_files
            count, alerts, _ = _step_detect_new_files(cur, now)

        conn.commit(); conn.close()
        assert alerts == 1
        assert mock_alert.call_args[0][0] == "CRITICAL"
        assert "RANSOM" in mock_alert.call_args[0][1]

    def test_known_files_not_flagged(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "known.zip"
        f.write_bytes(b"PK" + b"\x00" * 50)
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        _insert_record(db_env["db_path"], str(f), sha)

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT):
            from core.scanner import _step_detect_new_files
            count, alerts, _ = _step_detect_new_files(cur, now)

        conn.commit(); conn.close()
        assert count == 0


# =============================================================================
#   _step_check_backup_age
# =============================================================================

class TestStepCheckBackupAge:
    def test_fresh_backup_no_alert(self, db_env):
        backup_dir = db_env["backup_dir"]
        (backup_dir / "fresh.zip").write_bytes(b"PK" + b"\x00" * 50)

        with patch(PATCH_ALERT) as mock_alert:
            from core.scanner import _step_check_backup_age
            alerts = _step_check_backup_age()

        assert alerts == 0
        mock_alert.assert_not_called()

    def test_empty_folder_triggers_critical(self, db_env):
        # backup_dir exists but has no .zip or .bak files
        with patch(PATCH_ALERT) as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False):
            from core.scanner import _step_check_backup_age
            alerts = _step_check_backup_age()

        assert alerts == 1
        assert mock_alert.call_args[0][0] == "CRITICAL"

    def test_nonexistent_path_skipped(self, db_env, monkeypatch):
        import core.scanner as scanner_mod
        monkeypatch.setattr(scanner_mod, "BACKUP_PATHS", ["/no/such/path"])

        with patch(PATCH_ALERT) as mock_alert:
            from core.scanner import _step_check_backup_age
            alerts = _step_check_backup_age()

        assert alerts == 0
        mock_alert.assert_not_called()


# =============================================================================
#   _step_check_integrity
# =============================================================================

class TestStepCheckIntegrity:
    def test_valid_zip_passes(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "ok.zip"
        with zipfile.ZipFile(str(f), "w") as z:
            z.writestr("file.txt", "content")
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        _insert_record(db_env["db_path"], str(f), sha, status="OK")

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert:
            from core.scanner import _step_check_integrity
            alerts, _ = _step_check_integrity(cur, now)

        conn.commit(); conn.close()
        assert alerts == 0
        mock_alert.assert_not_called()

    def test_corrupt_zip_triggers_warning(self, db_env):
        backup_dir = db_env["backup_dir"]
        f = backup_dir / "bad.zip"
        f.write_bytes(b"PK\x03\x04" + b"\xff" * 200)
        _insert_record(db_env["db_path"], str(f), "abc123", status="OK")

        conn = _conn(db_env["db_path"])
        cur  = conn.cursor()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with patch(PATCH_ALERT) as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False):
            from core.scanner import _step_check_integrity
            alerts, _ = _step_check_integrity(cur, now)

        conn.commit(); conn.close()
        assert alerts == 1
        assert mock_alert.call_args[0][0] == "WARNING"

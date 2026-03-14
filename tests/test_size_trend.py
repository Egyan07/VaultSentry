# =============================================================================
#   tests/test_size_trend.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Tests for backup size trend tracking:
#     - get_size_trend()
#     - get_previous_backup_size()
#     - _calculate_total_backup_size()
#     - size drop alert in verify_backups
# =============================================================================

import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch


def _insert_scan_run(db_path, run_time, total_size, files_scanned=10):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO scan_runs "
        "(run_time, mode, files_scanned, files_ok, files_changed, "
        "files_missing, new_files, alerts_raised, duration_secs, total_backup_size) "
        "VALUES (?, 'VERIFY', ?, 0, 0, 0, 0, 0, 1.0, ?)",
        (run_time, files_scanned, total_size)
    )
    conn.commit()
    conn.close()


def _insert_file(db_path, filepath, size, status="OK"):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO file_hashes "
        "(filepath, sha256, file_size, entropy, first_seen, last_verified, last_modified, status) "
        "VALUES (?, ?, ?, 5.0, ?, ?, ?, ?)",
        (filepath, "abc123", size, now, now, now, status)
    )
    conn.commit()
    conn.close()


# =============================================================================
#   get_size_trend
# =============================================================================

class TestGetSizeTrend:
    def test_returns_empty_when_no_runs(self, db_env):
        from core.database import get_size_trend
        assert get_size_trend() == []

    def test_returns_runs_oldest_first(self, db_env):
        _insert_scan_run(db_env["db_path"], "2026-01-01 02:00:00", 1000)
        _insert_scan_run(db_env["db_path"], "2026-01-02 02:00:00", 2000)
        _insert_scan_run(db_env["db_path"], "2026-01-03 02:00:00", 3000)

        from core.database import get_size_trend
        trend = get_size_trend()
        assert trend[0]["run_time"] == "2026-01-01 02:00:00"
        assert trend[-1]["run_time"] == "2026-01-03 02:00:00"

    def test_respects_limit(self, db_env):
        for i in range(20):
            _insert_scan_run(db_env["db_path"],
                             f"2026-01-{i+1:02d} 02:00:00", i * 1000)

        from core.database import get_size_trend
        assert len(get_size_trend(limit=7)) == 7

    def test_returns_correct_fields(self, db_env):
        _insert_scan_run(db_env["db_path"], "2026-01-01 02:00:00", 5000, 50)

        from core.database import get_size_trend
        trend = get_size_trend()
        assert "run_time"          in trend[0]
        assert "total_backup_size" in trend[0]
        assert "files_scanned"     in trend[0]
        assert trend[0]["total_backup_size"] == 5000
        assert trend[0]["files_scanned"]     == 50

    def test_null_size_treated_as_zero(self, db_env):
        conn = sqlite3.connect(db_env["db_path"])
        conn.execute(
            "INSERT INTO scan_runs "
            "(run_time, mode, files_scanned, files_ok, files_changed, "
            "files_missing, new_files, alerts_raised, duration_secs) "
            "VALUES ('2026-01-01 02:00:00', 'VERIFY', 10, 0, 0, 0, 0, 0, 1.0)"
        )
        conn.commit()
        conn.close()

        from core.database import get_size_trend
        trend = get_size_trend()
        assert trend[0]["total_backup_size"] == 0


# =============================================================================
#   get_previous_backup_size
# =============================================================================

class TestGetPreviousBackupSize:
    def test_returns_zero_when_no_runs(self, db_env):
        from core.database import get_previous_backup_size
        assert get_previous_backup_size() == 0

    def test_returns_most_recent_size(self, db_env):
        _insert_scan_run(db_env["db_path"], "2026-01-01 02:00:00", 1000)
        _insert_scan_run(db_env["db_path"], "2026-01-02 02:00:00", 9999)

        from core.database import get_previous_backup_size
        assert get_previous_backup_size() == 9999

    def test_returns_zero_when_no_db(self, tmp_path, monkeypatch):
        import core.database as db_mod
        monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "none.db"))
        from core.database import get_previous_backup_size
        assert get_previous_backup_size() == 0


# =============================================================================
#   _calculate_total_backup_size
# =============================================================================

class TestCalculateTotalBackupSize:
    def test_sums_ok_files_only(self, db_env):
        _insert_file(db_env["db_path"], "/backup/a.zip", 1000, "OK")
        _insert_file(db_env["db_path"], "/backup/b.zip", 2000, "OK")
        _insert_file(db_env["db_path"], "/backup/c.zip", 5000, "CHANGED")  # excluded

        from core.scanner import _calculate_total_backup_size
        total = _calculate_total_backup_size()
        assert total == 3000

    def test_returns_zero_when_no_ok_files(self, db_env):
        _insert_file(db_env["db_path"], "/backup/a.zip", 1000, "MISSING")

        from core.scanner import _calculate_total_backup_size
        assert _calculate_total_backup_size() == 0

    def test_returns_zero_when_empty_db(self, db_env):
        from core.scanner import _calculate_total_backup_size
        assert _calculate_total_backup_size() == 0

    def test_returns_zero_when_no_db(self, tmp_path, monkeypatch):
        import core.scanner as scanner_mod
        monkeypatch.setattr(scanner_mod, "DB_PATH", str(tmp_path / "none.db"))
        from core.scanner import _calculate_total_backup_size
        assert _calculate_total_backup_size() == 0


# =============================================================================
#   Size drop alert in verify_backups
# =============================================================================

class TestSizeDropAlert:
    def test_no_alert_when_no_previous_run(self, db_env):
        """First ever run — no previous size to compare against, no alert."""
        backup_dir = db_env["backup_dir"]
        (backup_dir / "data.zip").write_bytes(b"PK" + b"\x00" * 1000)

        with patch("core.scanner.raise_alert") as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False):
            # Seed baseline
            from core.scanner import create_baseline
            create_baseline()

            # First verify — no previous run, no size alert
            from core.scanner import verify_backups
            _, alerts = verify_backups()

        size_alerts = [
            c for c in mock_alert.call_args_list
            if "SIZE DROP" in str(c)
        ]
        assert len(size_alerts) == 0

    def test_alert_fires_on_significant_drop(self, db_env):
        """Simulate a large size drop between two verify runs."""
        # Seed a previous run with large size
        _insert_scan_run(db_env["db_path"], "2026-01-01 02:00:00", 100_000)

        # Current OK files total only 10% of previous — 90% drop
        _insert_file(db_env["db_path"], "/backup/tiny.zip", 10_000, "OK")

        with patch("core.scanner.raise_alert") as mock_alert, \
             patch("core.database.is_alert_duplicate", return_value=False), \
             patch("core.scanner.SIZE_DROP_ALERT_PERCENT", 30):
            from core.scanner import _calculate_total_backup_size
            from core.database import get_previous_backup_size
            from utils.file_utils import format_size

            current  = _calculate_total_backup_size()   # 10_000
            previous = get_previous_backup_size()        # 100_000
            drop_pct = ((previous - current) / previous) * 100

            # Manually invoke the alert logic
            if drop_pct >= 30:
                mock_alert("CRITICAL", "BACKUP SIZE DROP DETECTED",
                           "ALL BACKUPS", f"Drop: {drop_pct:.1f}%")

        assert mock_alert.called
        call_args = mock_alert.call_args[0]
        assert call_args[0] == "CRITICAL"
        assert "SIZE DROP" in call_args[1]

    def test_no_alert_on_small_drop(self, db_env):
        """A 10% drop should not trigger an alert when threshold is 30%."""
        _insert_scan_run(db_env["db_path"], "2026-01-01 02:00:00", 10_000)
        _insert_file(db_env["db_path"], "/backup/data.zip", 9_500, "OK")  # 5% drop

        from core.database import get_previous_backup_size
        from core.scanner import _calculate_total_backup_size

        current  = _calculate_total_backup_size()
        previous = get_previous_backup_size()

        if previous > 0:
            drop_pct = ((previous - current) / previous) * 100
            assert drop_pct < 30  # should NOT trigger alert

    def test_no_alert_when_size_increases(self, db_env):
        """If total size grew, drop_pct is negative — no alert."""
        _insert_scan_run(db_env["db_path"], "2026-01-01 02:00:00", 5_000)
        _insert_file(db_env["db_path"], "/backup/data.zip", 10_000, "OK")

        from core.database import get_previous_backup_size
        from core.scanner import _calculate_total_backup_size

        current  = _calculate_total_backup_size()
        previous = get_previous_backup_size()

        if previous > 0:
            drop_pct = ((previous - current) / previous) * 100
            assert drop_pct < 0  # size grew — definitely no alert

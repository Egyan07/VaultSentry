# =============================================================================
#   tests/test_database.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import os
import sys
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch


@pytest.fixture
def tmp_db(db_env):
    return db_env["db_path"]


# =============================================================================
#   init_database
# =============================================================================

class TestInitDatabase:
    def test_creates_file_hashes_table(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        cur  = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_hashes'"
        )
        assert cur.fetchone() is not None
        conn.close()

    def test_creates_alerts_table(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        cur  = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'"
        )
        assert cur.fetchone() is not None
        conn.close()

    def test_creates_scan_runs_table(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        cur  = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_runs'"
        )
        assert cur.fetchone() is not None
        conn.close()

    def test_idempotent(self, tmp_db):
        from core.database import init_database
        init_database()  # second call must not raise

    def test_file_hashes_unique_constraint(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO file_hashes "
            "(filepath, sha256, file_size, entropy, first_seen, last_verified, last_modified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("/path/file.zip", "abc123", 1024, 5.0, now, now, now)
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO file_hashes "
                "(filepath, sha256, file_size, entropy, first_seen, last_verified, last_modified) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("/path/file.zip", "def456", 2048, 5.5, now, now, now)
            )
        conn.close()

    def test_alerts_table_columns(self, tmp_db):
        conn  = sqlite3.connect(tmp_db)
        cur   = conn.execute("PRAGMA table_info(alerts)")
        cols  = {row[1] for row in cur.fetchall()}
        expected = {"id", "timestamp", "severity", "alert_type", "filepath", "details"}
        assert expected.issubset(cols)
        conn.close()


# =============================================================================
#   baseline_exists
# =============================================================================

class TestBaselineExists:
    def test_returns_false_when_no_db(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "nonexistent.db"))
        from core.database import baseline_exists
        assert baseline_exists() is False

    def test_returns_false_when_empty(self, tmp_db):
        from core.database import baseline_exists
        assert baseline_exists() is False

    def test_returns_true_when_has_records(self, tmp_db):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO file_hashes "
            "(filepath, sha256, file_size, entropy, first_seen, last_verified, last_modified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("/backup/file.zip", "abc", 100, 5.0, now, now, now)
        )
        conn.commit()
        conn.close()
        from core.database import baseline_exists
        assert baseline_exists() is True


# =============================================================================
#   is_alert_duplicate
# =============================================================================

class TestIsAlertDuplicate:
    def test_no_prior_alerts_returns_false(self, tmp_db):
        from core.database import is_alert_duplicate
        assert is_alert_duplicate("BACKUP FILE MISSING", "/path/file.zip") is False

    def test_recent_alert_returns_true(self, tmp_db):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, "CRITICAL", "BACKUP FILE MISSING", "/path/file.zip", "gone")
        )
        conn.commit()
        conn.close()
        from core.database import is_alert_duplicate
        assert is_alert_duplicate("BACKUP FILE MISSING", "/path/file.zip") is True

    def test_old_alert_returns_false(self, tmp_db):
        old = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (old, "CRITICAL", "BACKUP FILE MISSING", "/path/file.zip", "gone")
        )
        conn.commit()
        conn.close()
        from core.database import is_alert_duplicate
        assert is_alert_duplicate("BACKUP FILE MISSING", "/path/file.zip") is False

    def test_different_filepath_not_duplicate(self, tmp_db):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, "CRITICAL", "BACKUP FILE MISSING", "/path/other.zip", "gone")
        )
        conn.commit()
        conn.close()
        from core.database import is_alert_duplicate
        assert is_alert_duplicate("BACKUP FILE MISSING", "/path/file.zip") is False

    def test_different_alert_type_not_duplicate(self, tmp_db):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, "CRITICAL", "STALE BACKUP", "/path/file.zip", "old")
        )
        conn.commit()
        conn.close()
        from core.database import is_alert_duplicate
        assert is_alert_duplicate("BACKUP FILE MISSING", "/path/file.zip") is False


# =============================================================================
#   save_alert
# =============================================================================

class TestSaveAlert:
    def test_saves_to_db(self, tmp_db):
        from core.database import save_alert
        save_alert("2026-01-01 12:00:00", "CRITICAL",
                   "TEST ALERT", "/path/file.zip", "test details")
        conn = sqlite3.connect(tmp_db)
        cur  = conn.execute(
            "SELECT severity, alert_type, filepath FROM alerts "
            "WHERE alert_type='TEST ALERT'"
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "CRITICAL"
        assert row[2] == "/path/file.zip"


# =============================================================================
#   save_scan_run + get_stats
# =============================================================================

class TestSaveScanRun:
    def test_saves_and_stats_reflect_it(self, tmp_db):
        from core.database import save_scan_run, get_stats
        save_scan_run("2026-01-01 02:00:00", 100, 95, 3, 2, 5, 1, 12.5)
        stats = get_stats()
        assert stats["last_run"] is not None
        assert stats["last_run"][1] == 100
        assert stats["last_run"][2] == 12.5

    def test_get_stats_empty_db(self, tmp_db):
        from core.database import get_stats
        stats = get_stats()
        assert stats["total"]   == 0
        assert stats["ok"]      == 0
        assert stats["changed"] == 0
        assert stats["missing"] == 0


# =============================================================================
#   get_recent_alerts
# =============================================================================

class TestGetRecentAlerts:
    def test_returns_empty_list_when_no_alerts(self, tmp_db):
        from core.database import get_recent_alerts
        assert get_recent_alerts() == []

    def test_returns_alerts_most_recent_first(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        for i, ts in enumerate(["2026-01-01 10:00:00", "2026-01-02 10:00:00"]):
            conn.execute(
                "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, "WARNING", f"ALERT_{i}", "/path/f.zip", "detail")
            )
        conn.commit()
        conn.close()
        from core.database import get_recent_alerts
        alerts = get_recent_alerts()
        assert len(alerts) == 2
        assert alerts[0]["timestamp"] == "2026-01-02 10:00:00"

    def test_respects_limit(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        for i in range(10):
            conn.execute(
                "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"2026-01-{i+1:02d} 10:00:00", "INFO", "TEST", "/f.zip", "d")
            )
        conn.commit()
        conn.close()
        from core.database import get_recent_alerts
        assert len(get_recent_alerts(limit=5)) == 5

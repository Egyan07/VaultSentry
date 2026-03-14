# =============================================================================
#   tests/test_alerts.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch, MagicMock


class TestRaiseAlert:
    def test_alert_saved_to_db(self, db_env):
        with patch("subprocess.run"), \
             patch("core.alerts.TKINTER_AVAILABLE", False):
            from core.alerts import raise_alert
            raise_alert("CRITICAL", "TEST ALERT", "/path/file.zip", "details here")

        conn = sqlite3.connect(db_env["db_path"])
        cur  = conn.execute(
            "SELECT severity, alert_type FROM alerts WHERE alert_type='TEST ALERT'"
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "CRITICAL"

    def test_duplicate_suppressed(self, db_env):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(db_env["db_path"])
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, "CRITICAL", "BACKUP FILE MISSING", "/path/file.zip", "gone")
        )
        conn.commit()
        conn.close()

        with patch("subprocess.run"), \
             patch("core.alerts.TKINTER_AVAILABLE", False):
            from core.alerts import raise_alert
            raise_alert("CRITICAL", "BACKUP FILE MISSING",
                        "/path/file.zip", "still gone")

        conn = sqlite3.connect(db_env["db_path"])
        cur  = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_type='BACKUP FILE MISSING'"
        )
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1

    def test_different_filepath_not_suppressed(self, db_env):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(db_env["db_path"])
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, "CRITICAL", "BACKUP FILE MISSING", "/path/file1.zip", "gone")
        )
        conn.commit()
        conn.close()

        with patch("subprocess.run"), \
             patch("core.alerts.TKINTER_AVAILABLE", False):
            from core.alerts import raise_alert
            raise_alert("CRITICAL", "BACKUP FILE MISSING",
                        "/path/file2.zip", "also gone")

        conn = sqlite3.connect(db_env["db_path"])
        cur  = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_type='BACKUP FILE MISSING'"
        )
        count = cur.fetchone()[0]
        conn.close()
        assert count == 2

    def test_msg_exe_failure_does_not_raise(self, db_env):
        with patch("subprocess.run", side_effect=FileNotFoundError("msg not found")), \
             patch("core.alerts.TKINTER_AVAILABLE", False):
            from core.alerts import raise_alert
            raise_alert("WARNING", "STALE BACKUP", "/path/", "old")

    def test_email_skipped_when_disabled(self, db_env):
        with patch("subprocess.run"), \
             patch("core.alerts.TKINTER_AVAILABLE", False), \
             patch("smtplib.SMTP") as mock_smtp:
            from core.alerts import raise_alert
            raise_alert("CRITICAL", "TEST", "/f.zip", "detail")
        mock_smtp.assert_not_called()

    def test_email_uses_ssl_context(self, db_env, monkeypatch):
        import config
        monkeypatch.setattr(config, "EMAIL_ENABLED",    True)
        monkeypatch.setattr(config, "EMAIL_FROM",       "test@test.com")
        monkeypatch.setattr(config, "EMAIL_TO",         "admin@test.com")
        monkeypatch.setattr(config, "EMAIL_SMTP_SERVER","smtp.test.com")
        monkeypatch.setattr(config, "EMAIL_SMTP_PORT",  587)

        mock_server  = MagicMock()
        mock_context = MagicMock()

        with patch("subprocess.run"), \
             patch("core.alerts.TKINTER_AVAILABLE", False), \
             patch("os.environ.get", return_value="testpassword"), \
             patch("ssl.create_default_context", return_value=mock_context) as mock_ssl, \
             patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
            mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)

            from core.alerts import _send_email
            _send_email("CRITICAL", "TEST", "alert body")

        mock_ssl.assert_called_once()
        mock_server.starttls.assert_called_once_with(context=mock_context)

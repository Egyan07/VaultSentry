# =============================================================================
#   tests/test_digest.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Tests for core/digest.py
#   All SMTP calls are mocked — no real emails sent.
# =============================================================================

import os
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch, MagicMock

from core.digest import (
    build_digest_html, build_digest_text,
    should_send_digest, mark_digest_sent, send_digest,
)


# =============================================================================
#   Fixtures
# =============================================================================

@pytest.fixture
def sample_data():
    return {
        "alerts": [
            {
                "timestamp":  "2026-03-15 02:01:00",
                "severity":   "CRITICAL",
                "alert_type": "BACKUP FILE MISSING",
                "filepath":   "D:\\Backups\\ClientA\\data.zip",
                "details":    "File no longer exists",
            },
            {
                "timestamp":  "2026-03-15 02:01:05",
                "severity":   "WARNING",
                "alert_type": "BACKUP FILE MODIFIED",
                "filepath":   "D:\\Backups\\ClientB\\report.xlsx",
                "details":    "Hash changed since baseline",
            },
        ],
        "last_run": {
            "run_time":          "2026-03-15 02:00:00",
            "files_scanned":     150,
            "files_ok":          148,
            "files_changed":     1,
            "files_missing":     1,
            "alerts_raised":     2,
            "duration_secs":     12.4,
            "total_backup_size": 524288000,  # 500 MB
        },
        "stats": {
            "total": 150, "ok": 148, "changed": 1,
            "missing": 1, "corrupt": 0, "new": 0,
            "crit_alerts": 5, "warn_alerts": 3, "last_run": None,
        }
    }


@pytest.fixture
def empty_data():
    return {
        "alerts":   [],
        "last_run": None,
        "stats":    {"total": 0, "ok": 0, "changed": 0, "missing": 0,
                     "corrupt": 0, "new": 0, "crit_alerts": 0,
                     "warn_alerts": 0, "last_run": None},
    }


# =============================================================================
#   build_digest_html
# =============================================================================

class TestBuildDigestHtml:
    def test_returns_string(self, sample_data):
        html = build_digest_html(sample_data)
        assert isinstance(html, str)
        assert len(html) > 100

    def test_contains_app_name(self, sample_data):
        html = build_digest_html(sample_data)
        assert "VaultSentry" in html

    def test_critical_banner_when_critical_alerts(self, sample_data):
        html = build_digest_html(sample_data)
        assert "CRITICAL" in html
        assert "#ff4444" in html  # critical colour

    def test_all_clear_banner_when_no_alerts(self, empty_data):
        html = build_digest_html(empty_data)
        assert "All Clear" in html or "No Issues" in html
        assert "#00c97a" in html  # green

    def test_warning_banner_when_only_warnings(self, sample_data):
        data = dict(sample_data)
        data["alerts"] = [a for a in sample_data["alerts"]
                          if a["severity"] == "WARNING"]
        html = build_digest_html(data)
        assert "Warning" in html

    def test_scan_summary_present(self, sample_data):
        html = build_digest_html(sample_data)
        assert "150" in html   # files scanned
        assert "148" in html   # files ok
        assert "12.4s" in html # duration

    def test_alert_rows_present(self, sample_data):
        html = build_digest_html(sample_data)
        assert "BACKUP FILE MISSING" in html
        assert "BACKUP FILE MODIFIED" in html
        assert "ClientA" in html

    def test_size_formatted(self, sample_data):
        html = build_digest_html(sample_data)
        assert "MB" in html or "GB" in html  # size was formatted

    def test_no_scan_run_handled_gracefully(self, empty_data):
        html = build_digest_html(empty_data)
        assert "No scan runs found" in html

    def test_caps_alerts_at_50(self, sample_data):
        """HTML should note when alerts are capped."""
        data = dict(sample_data)
        data["alerts"] = [
            {"timestamp": "2026-01-01", "severity": "WARNING",
             "alert_type": f"ALERT_{i}", "filepath": f"/f{i}.zip",
             "details": "detail"}
            for i in range(60)
        ]
        html = build_digest_html(data)
        assert "50" in html  # cap note


# =============================================================================
#   build_digest_text
# =============================================================================

class TestBuildDigestText:
    def test_returns_string(self, sample_data):
        text = build_digest_text(sample_data)
        assert isinstance(text, str)

    def test_contains_app_name(self, sample_data):
        assert "VaultSentry" in build_digest_text(sample_data)

    def test_critical_status_line(self, sample_data):
        text = build_digest_text(sample_data)
        assert "CRITICAL" in text

    def test_all_clear_when_no_alerts(self, empty_data):
        text = build_digest_text(empty_data)
        assert "no issues" in text.lower() or "all clear" in text.lower() or "all backup" in text.lower()

    def test_alert_lines_included(self, sample_data):
        text = build_digest_text(sample_data)
        assert "BACKUP FILE MISSING" in text
        assert "ClientA" in text

    def test_no_alerts_message(self, empty_data):
        text = build_digest_text(empty_data)
        assert "No alerts" in text

    def test_scan_summary_in_text(self, sample_data):
        text = build_digest_text(sample_data)
        assert "150" in text   # files scanned
        assert "148" in text   # files ok

    def test_no_scan_run_handled(self, empty_data):
        text = build_digest_text(empty_data)
        assert "No scan runs" in text


# =============================================================================
#   should_send_digest / mark_digest_sent
# =============================================================================

class TestShouldSendDigest:
    def test_returns_false_when_disabled(self, monkeypatch):
        import core.digest as digest_mod
        monkeypatch.setattr(digest_mod, "DIGEST_ENABLED", False)
        monkeypatch.setattr(digest_mod, "_last_digest_date", None)
        assert should_send_digest() is False

    def test_returns_false_before_digest_time(self, monkeypatch):
        import core.digest as digest_mod
        monkeypatch.setattr(digest_mod, "DIGEST_ENABLED",    True)
        monkeypatch.setattr(digest_mod, "DIGEST_TIME",       14)
        monkeypatch.setattr(digest_mod, "_last_digest_date", None)

        fake_now = datetime.now().replace(hour=10, minute=0)
        assert should_send_digest(now=fake_now) is False

    def test_returns_true_at_digest_time(self, monkeypatch):
        import core.digest as digest_mod
        monkeypatch.setattr(digest_mod, "DIGEST_ENABLED",    True)
        monkeypatch.setattr(digest_mod, "DIGEST_TIME",       8)
        monkeypatch.setattr(digest_mod, "_last_digest_date", None)

        fake_now = datetime.now().replace(hour=9, minute=0)
        assert should_send_digest(now=fake_now) is True

    def test_returns_false_if_already_sent_today(self, monkeypatch):
        import core.digest as digest_mod
        fake_now = datetime.now().replace(hour=10)
        today    = fake_now.date()

        monkeypatch.setattr(digest_mod, "DIGEST_ENABLED",    True)
        monkeypatch.setattr(digest_mod, "DIGEST_TIME",       0)
        monkeypatch.setattr(digest_mod, "_last_digest_date", today)

        assert should_send_digest(now=fake_now) is False

    def test_mark_digest_sent_sets_date(self, monkeypatch):
        import core.digest as digest_mod
        monkeypatch.setattr(digest_mod, "_last_digest_date", None)
        mark_digest_sent()
        assert digest_mod._last_digest_date == datetime.now().date()


# =============================================================================
#   send_digest
# =============================================================================

class TestSendDigest:
    def test_returns_false_when_no_password(self, db_env, monkeypatch):
        monkeypatch.setenv("VAULTSENTRY_EMAIL_PASSWORD", "")
        with patch("os.environ.get", return_value=""):
            result = send_digest()
        assert result is False

    def test_sends_email_with_ssl_context(self, db_env, monkeypatch):
        import ssl
        mock_server  = MagicMock()
        mock_context = MagicMock()

        monkeypatch.setattr("core.digest.EMAIL_FROM",        "from@test.com")
        monkeypatch.setattr("core.digest.EMAIL_TO",          "to@test.com")
        monkeypatch.setattr("core.digest.EMAIL_SMTP_SERVER", "smtp.test.com")
        monkeypatch.setattr("core.digest.EMAIL_SMTP_PORT",   587)

        with patch("os.environ.get", return_value="testpassword"), \
             patch("ssl.create_default_context", return_value=mock_context) as mock_ssl, \
             patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
            mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)

            result = send_digest()

        mock_ssl.assert_called_once()
        mock_server.starttls.assert_called_once_with(context=mock_context)
        assert result is True

    def test_returns_false_on_smtp_error(self, db_env):
        import smtplib
        with patch("os.environ.get", return_value="testpassword"), \
             patch("smtplib.SMTP", side_effect=smtplib.SMTPException("fail")):
            result = send_digest()
        assert result is False

    def test_digest_contains_both_parts(self, db_env):
        """Email should have both HTML and plain-text parts."""
        sent_messages = []

        def fake_sendmail(from_addr, to_addr, msg_str):
            sent_messages.append(msg_str)

        mock_server = MagicMock()
        mock_server.sendmail.side_effect = fake_sendmail

        with patch("os.environ.get", return_value="testpassword"), \
             patch("ssl.create_default_context"), \
             patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
            mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)
            send_digest()

        assert len(sent_messages) == 1
        assert "text/html" in sent_messages[0]
        assert "text/plain" in sent_messages[0]


# =============================================================================
#   get_digest_data (integration with DB)
# =============================================================================

class TestGetDigestData:
    def test_returns_correct_structure(self, db_env):
        from core.database import get_digest_data
        data = get_digest_data()
        assert "alerts"   in data
        assert "last_run" in data
        assert "stats"    in data

    def test_returns_alerts_within_window(self, db_env):
        import sqlite3
        conn = sqlite3.connect(db_env["db_path"])
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        old  = (datetime.now() - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, "CRITICAL", "RECENT ALERT", "/f.zip", "detail")
        )
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (old, "WARNING", "OLD ALERT", "/g.zip", "old detail")
        )
        conn.commit()
        conn.close()

        from core.database import get_digest_data
        data = get_digest_data(since_hours=25)

        alert_types = [a["alert_type"] for a in data["alerts"]]
        assert "RECENT ALERT" in alert_types
        assert "OLD ALERT"    not in alert_types

    def test_no_db_returns_empty(self, tmp_path, monkeypatch):
        import core.database as db_mod
        monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "none.db"))
        from core.database import get_digest_data
        data = get_digest_data()
        assert data["alerts"]   == []
        assert data["last_run"] is None

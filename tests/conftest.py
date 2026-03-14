# =============================================================================
#   tests/conftest.py — VaultSentry v1.0
#   Shared pytest fixtures used across all test modules.
# =============================================================================

import os
import sys
import importlib
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """
    Fully isolated environment per test.
    monkeypatch sets config attributes before any import uses them,
    and stays active for the entire test.
    """
    db_path    = str(tmp_path / "vault.db")
    log_dir    = str(tmp_path / "logs")
    log_file   = str(tmp_path / "logs" / "vault.log")
    backup_dir = tmp_path / "backups"

    os.makedirs(log_dir,    exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    # Patch config module attributes directly — works regardless of import order
    import config
    monkeypatch.setattr(config, "DB_PATH",                db_path)
    monkeypatch.setattr(config, "LOG_DIR",                log_dir)
    monkeypatch.setattr(config, "LOG_FILE",               log_file)
    monkeypatch.setattr(config, "BACKUP_PATHS",           [str(backup_dir)])
    monkeypatch.setattr(config, "MONITORED_EXTENSIONS",   [".zip", ".bak"])
    monkeypatch.setattr(config, "MAX_BACKUP_AGE_HOURS",   25)
    monkeypatch.setattr(config, "ENTROPY_SPIKE_THRESHOLD", 7.8)
    monkeypatch.setattr(config, "ALERT_COOLDOWN_HOURS",   24)
    monkeypatch.setattr(config, "ADMIN_PC",               "TESTPC")
    monkeypatch.setattr(config, "EMAIL_ENABLED",          False)
    monkeypatch.setattr(config, "SIZE_DROP_ALERT_PERCENT", 30)

    import core.database as db_mod
    import core.alerts   as alerts_mod
    import core.scanner  as scanner_mod
    import core.restore  as restore_mod

    monkeypatch.setattr(db_mod,      "DB_PATH",               db_path)
    monkeypatch.setattr(restore_mod, "DB_PATH",               db_path)
    monkeypatch.setattr(restore_mod, "BACKUP_PATHS",          [str(backup_dir)])
    monkeypatch.setattr(scanner_mod, "DB_PATH",               db_path)  if hasattr(scanner_mod, "DB_PATH")               else None
    monkeypatch.setattr(scanner_mod, "BACKUP_PATHS",          [str(backup_dir)]) if hasattr(scanner_mod, "BACKUP_PATHS") else None
    monkeypatch.setattr(scanner_mod, "MONITORED_EXTENSIONS",  [".zip", ".bak"])  if hasattr(scanner_mod, "MONITORED_EXTENSIONS") else None
    monkeypatch.setattr(scanner_mod, "MAX_BACKUP_AGE_HOURS",  25)                if hasattr(scanner_mod, "MAX_BACKUP_AGE_HOURS")  else None
    monkeypatch.setattr(scanner_mod, "ENTROPY_SPIKE_THRESHOLD", 7.8)             if hasattr(scanner_mod, "ENTROPY_SPIKE_THRESHOLD") else None
    monkeypatch.setattr(scanner_mod, "SIZE_DROP_ALERT_PERCENT", 30)              if hasattr(scanner_mod, "SIZE_DROP_ALERT_PERCENT") else None

    # Init the database at the patched path
    db_mod.init_database()

    return {
        "db_path":    db_path,
        "log_dir":    log_dir,
        "backup_dir": backup_dir,
        "tmp_path":   tmp_path,
    }

# =============================================================================
#   core/database.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import os
import sqlite3
from datetime import datetime, timedelta

from config import DB_PATH, ALERT_COOLDOWN_HOURS
from logger import log
from logger import log


def init_database():
    """Create all tables if they don't already exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath        TEXT UNIQUE,
            sha256          TEXT,
            file_size       INTEGER,
            entropy         REAL,
            first_seen      TEXT,
            last_verified   TEXT,
            last_modified   TEXT,
            status          TEXT DEFAULT 'OK'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            severity    TEXT,
            alert_type  TEXT,
            filepath    TEXT,
            details     TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scan_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time        TEXT,
            mode            TEXT,
            files_scanned   INTEGER,
            files_ok        INTEGER,
            files_changed   INTEGER,
            files_missing   INTEGER,
            new_files       INTEGER,
            alerts_raised   INTEGER,
            duration_secs   REAL
        )
    """)

    # Snapshot registry — one row per saved snapshot
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            file_count  INTEGER DEFAULT 0,
            notes       TEXT DEFAULT ''
        )
    """)

    # Snapshot file records — one row per file per snapshot
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_files (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id   INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
            filepath      TEXT NOT NULL,
            sha256        TEXT,
            file_size     INTEGER,
            entropy       REAL,
            status        TEXT,
            last_modified TEXT
        )
    """)

    # Add total_backup_size to scan_runs if it doesn't exist yet (migration)
    try:
        cur.execute("ALTER TABLE scan_runs ADD COLUMN total_backup_size INTEGER DEFAULT 0")
    except Exception:
        pass  # Column already exists

    conn.commit()
    conn.close()
    log.info("Database initialised at: %s", DB_PATH)


def baseline_exists() -> bool:
    """Return True if at least one file has been recorded in the baseline."""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn  = sqlite3.connect(DB_PATH)
        cur   = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM file_hashes")
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def save_scan_run(run_time, total_scanned, files_ok, files_changed,
                  files_missing, new_files, alerts_raised, duration,
                  total_backup_size: int = 0):
    """Persist a scan run summary record to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO scan_runs
                (run_time, mode, files_scanned, files_ok, files_changed,
                 files_missing, new_files, alerts_raised, duration_secs,
                 total_backup_size)
            VALUES (?, 'VERIFY', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_time, total_scanned, files_ok, files_changed,
              files_missing, new_files, alerts_raised, duration,
              total_backup_size))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Could not save scan run: %s", e)


def is_alert_duplicate(alert_type: str, filepath: str) -> bool:
    """
    Return True if the same alert_type + filepath was already raised
    within ALERT_COOLDOWN_HOURS. Prevents nightly spam for unchanged issues.
    """
    try:
        cutoff = (datetime.now() - timedelta(hours=ALERT_COOLDOWN_HOURS)
                  ).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM alerts "
            "WHERE alert_type=? AND filepath=? AND timestamp > ?",
            (alert_type, filepath, cutoff)
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def save_alert(timestamp, severity, alert_type, filepath, details):
    """Write a new alert record to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO alerts (timestamp, severity, alert_type, filepath, details) "
            "VALUES (?,?,?,?,?)",
            (timestamp, severity, alert_type, filepath, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Failed to save alert to DB: %s", e)


def get_stats() -> dict:
    """Return current counts for the dashboard."""
    if not os.path.exists(DB_PATH):
        return {"ok": 0, "changed": 0, "missing": 0, "corrupt": 0, "new": 0,
                "crit_alerts": 0, "warn_alerts": 0, "last_run": None,
                "total": 0}
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    def count(where):
        cur.execute(f"SELECT COUNT(*) FROM file_hashes WHERE {where}")
        return cur.fetchone()[0]

    stats = {
        "total":   count("1=1"),
        "ok":      count("status='OK'"),
        "changed": count("status='CHANGED'"),
        "missing": count("status='MISSING'"),
        "corrupt": count("status='CORRUPT'"),
        "new":     count("status='NEW'"),
    }

    cur.execute("SELECT COUNT(*) FROM alerts WHERE severity='CRITICAL'")
    stats["crit_alerts"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM alerts WHERE severity='WARNING'")
    stats["warn_alerts"] = cur.fetchone()[0]

    cur.execute(
        "SELECT run_time, files_scanned, duration_secs "
        "FROM scan_runs ORDER BY id DESC LIMIT 1"
    )
    stats["last_run"] = cur.fetchone()
    conn.close()
    return stats


def get_recent_alerts(limit: int = 100) -> list[dict]:
    """Return the most recent alerts for the alerts tab."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT timestamp, severity, alert_type, filepath, details "
        "FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"timestamp": r[0], "severity": r[1], "alert_type": r[2],
         "filepath": r[3], "details": r[4]}
        for r in rows
    ]


# =============================================================================
#   Snapshot functions
# =============================================================================

def get_digest_data(since_hours: int = 25) -> dict:
    """
    Collect all data needed for the daily digest email:
      - alerts raised in the last `since_hours`
      - last scan run summary
      - overall stats

    since_hours=25 covers the last nightly run even if it ran slightly
    before 24h ago.
    """
    if not os.path.exists(DB_PATH):
        return {"alerts": [], "last_run": None, "stats": get_stats()}

    cutoff = (
        datetime.now() - timedelta(hours=since_hours)
    ).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Alerts since cutoff
    cur.execute(
        "SELECT timestamp, severity, alert_type, filepath, details "
        "FROM alerts WHERE timestamp > ? ORDER BY severity DESC, timestamp DESC",
        (cutoff,)
    )
    alerts = [
        {"timestamp": r[0], "severity": r[1], "alert_type": r[2],
         "filepath": r[3], "details": r[4]}
        for r in cur.fetchall()
    ]

    # Last scan run
    cur.execute(
        "SELECT run_time, files_scanned, files_ok, files_changed, "
        "files_missing, alerts_raised, duration_secs, total_backup_size "
        "FROM scan_runs WHERE mode='VERIFY' ORDER BY id DESC LIMIT 1"
    )
    row      = cur.fetchone()
    last_run = None
    if row:
        last_run = {
            "run_time":          row[0],
            "files_scanned":     row[1],
            "files_ok":          row[2],
            "files_changed":     row[3],
            "files_missing":     row[4],
            "alerts_raised":     row[5],
            "duration_secs":     row[6],
            "total_backup_size": row[7] or 0,
        }

    conn.close()

    return {
        "alerts":   alerts,
        "last_run": last_run,
        "stats":    get_stats(),
    }


def get_size_trend(limit: int = 14) -> list[dict]:
    """
    Return the last N scan runs with their backup sizes for trend analysis.
    Used to detect sudden drops in total backup size.
    Returns oldest-first so charts render left-to-right.
    """
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT run_time, total_backup_size, files_scanned "
        "FROM scan_runs WHERE mode='VERIFY' "
        "ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"run_time": r[0], "total_backup_size": r[1] or 0,
         "files_scanned": r[2] or 0}
        for r in reversed(rows)  # oldest first
    ]


def get_previous_backup_size() -> int:
    """Return the total_backup_size from the most recent completed scan run."""
    if not os.path.exists(DB_PATH):
        return 0
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT total_backup_size FROM scan_runs "
            "WHERE mode='VERIFY' ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else 0
    except Exception:
        return 0


# =============================================================================
#   Snapshot functions
# =============================================================================

def create_snapshot(label: str, notes: str = "") -> int:
    """
    Copy the current file_hashes table into a new snapshot.
    Returns the new snapshot_id.

    A snapshot is a point-in-time copy of all known file records.
    Re-running baseline or verify does not overwrite snapshots —
    they are immutable once created.
    """
    if not os.path.exists(DB_PATH):
        log.warning("create_snapshot: no database found")
        return -1

    conn       = sqlite3.connect(DB_PATH)
    cur        = conn.cursor()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert snapshot header
    cur.execute(
        "INSERT INTO snapshots (label, created_at, notes) VALUES (?, ?, ?)",
        (label, created_at, notes)
    )
    snapshot_id = cur.lastrowid

    # Copy current file_hashes into snapshot_files
    cur.execute("""
        INSERT INTO snapshot_files
            (snapshot_id, filepath, sha256, file_size, entropy, status, last_modified)
        SELECT ?, filepath, sha256, file_size, entropy, status, last_modified
        FROM file_hashes
    """, (snapshot_id,))

    file_count = cur.rowcount

    # Update snapshot with file count
    cur.execute(
        "UPDATE snapshots SET file_count=? WHERE id=?",
        (file_count, snapshot_id)
    )

    conn.commit()
    conn.close()

    log.info("Snapshot created: id=%d label=%r files=%d", snapshot_id, label, file_count)
    return snapshot_id


def list_snapshots() -> list[dict]:
    """Return all snapshots, most recent first."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT id, label, created_at, file_count, notes "
        "FROM snapshots ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "label": r[1], "created_at": r[2],
         "file_count": r[3], "notes": r[4]}
        for r in rows
    ]


def get_snapshot_files(snapshot_id: int) -> list[dict]:
    """Return all file records for a given snapshot."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT filepath, sha256, file_size, entropy, status, last_modified "
        "FROM snapshot_files WHERE snapshot_id=? ORDER BY filepath",
        (snapshot_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"filepath": r[0], "sha256": r[1], "file_size": r[2],
         "entropy": r[3], "status": r[4], "last_modified": r[5]}
        for r in rows
    ]


def diff_snapshots(snap_id_a: int, snap_id_b: int) -> dict:
    """
    Compare two snapshots and return a diff.

    Returns a dict with:
      added   — files in B but not in A
      removed — files in A but not in B
      changed — files in both but with different sha256
      unchanged — files identical in both
    """
    files_a = {f["filepath"]: f for f in get_snapshot_files(snap_id_a)}
    files_b = {f["filepath"]: f for f in get_snapshot_files(snap_id_b)}

    added     = []
    removed   = []
    changed   = []
    unchanged = []

    all_paths = set(files_a.keys()) | set(files_b.keys())

    for path in sorted(all_paths):
        in_a = path in files_a
        in_b = path in files_b

        if in_b and not in_a:
            added.append(files_b[path])
        elif in_a and not in_b:
            removed.append(files_a[path])
        elif in_a and in_b:
            if files_a[path]["sha256"] != files_b[path]["sha256"]:
                changed.append({
                    "filepath":    path,
                    "sha256_a":    files_a[path]["sha256"],
                    "sha256_b":    files_b[path]["sha256"],
                    "size_a":      files_a[path]["file_size"],
                    "size_b":      files_b[path]["file_size"],
                    "entropy_a":   files_a[path]["entropy"],
                    "entropy_b":   files_b[path]["entropy"],
                })
            else:
                unchanged.append(files_a[path])

    return {
        "added":     added,
        "removed":   removed,
        "changed":   changed,
        "unchanged": unchanged,
    }


def delete_snapshot(snapshot_id: int) -> bool:
    """Delete a snapshot and all its file records. Returns True on success."""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        # Enable foreign key cascade delete
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,))
        conn.commit()
        conn.close()
        log.info("Snapshot %d deleted", snapshot_id)
        return True
    except Exception as e:
        log.error("Failed to delete snapshot %d: %s", snapshot_id, e)
        return False

# =============================================================================
#   core/scanner.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Core scanning logic: baseline creation and nightly verification.
#   Four verification steps, each independently testable.
# =============================================================================

import os
import sys
import time
import sqlite3
from datetime import datetime

from config import (
    BACKUP_PATHS, MONITORED_EXTENSIONS,
    MAX_BACKUP_AGE_HOURS, ENTROPY_SPIKE_THRESHOLD,
    SIZE_DROP_ALERT_PERCENT, DB_PATH,
)
from logger import log
from core.database import baseline_exists, save_scan_run, get_previous_backup_size
from core.alerts import raise_alert
from utils.file_utils import (
    calculate_sha256, calculate_entropy,
    get_file_list, is_file_openable, format_size,
)


# =============================================================================
#   BASELINE
# =============================================================================

def create_baseline(progress_callback=None):
    """
    Walk all backup paths, hash every file, and store as known-good baseline.
    Re-running updates all existing records.
    progress_callback(current, total, filepath) for GUI progress updates.
    """
    log.info("=" * 70)
    log.info("VaultSentry v1.0 — BASELINE MODE")
    log.info("Red Parrot Accounting Ltd")
    log.info("=" * 70)
    log.info("Building baseline hash database...")

    start_time = time.time()
    files      = get_file_list(BACKUP_PATHS, MONITORED_EXTENSIONS)

    if not files:
        log.warning("No files found in configured backup paths.")
        log.warning("Check BACKUP_PATHS in config.py. Current: %s", BACKUP_PATHS)
        return 0

    log.info("Found %d files to baseline.", len(files))

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    processed = 0
    skipped   = 0

    for idx, filepath in enumerate(files):
        if progress_callback:
            progress_callback(idx + 1, len(files), filepath)
        try:
            sha256 = calculate_sha256(filepath)
            if sha256 is None:
                skipped += 1
                continue

            entropy   = calculate_entropy(filepath)
            file_size = os.path.getsize(filepath)
            modified  = datetime.fromtimestamp(
                os.path.getmtime(filepath)
            ).strftime("%Y-%m-%d %H:%M:%S")

            cur.execute("""
                INSERT INTO file_hashes
                    (filepath, sha256, file_size, entropy,
                     first_seen, last_verified, last_modified, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OK')
                ON CONFLICT(filepath) DO UPDATE SET
                    sha256        = excluded.sha256,
                    file_size     = excluded.file_size,
                    entropy       = excluded.entropy,
                    last_verified = excluded.last_verified,
                    last_modified = excluded.last_modified,
                    status        = 'OK'
            """, (filepath, sha256, file_size, entropy, now, now, modified))

            processed += 1
            if processed % 50 == 0:
                log.info("  Baselined %d / %d files...", processed, len(files))

        except Exception as e:
            log.error("Error processing %s: %s", filepath, e)
            skipped += 1

    conn.commit()
    conn.close()

    duration = round(time.time() - start_time, 2)
    log.info("-" * 70)
    log.info("Baseline complete.")
    log.info("  Files baselined : %d", processed)
    log.info("  Files skipped   : %d", skipped)
    log.info("  Duration        : %s seconds", duration)
    log.info("  Database        : %s", DB_PATH)
    log.info("Run nightly checks with: python main.py --verify")
    log.info("=" * 70)
    return processed


# =============================================================================
#   VERIFY
# =============================================================================

def verify_backups(progress_callback=None):
    """
    Nightly verification — compares current files against the stored baseline.
    progress_callback(step, message) for GUI progress updates.
    Returns (results, alerts_raised).
    """
    if not baseline_exists():
        log.error("No baseline found. Run --baseline first.")
        print("\n[ERROR] No baseline found. Run: python main.py --baseline\n")
        sys.exit(1)

    log.info("=" * 70)
    log.info("VaultSentry v1.0 — NIGHTLY VERIFICATION")
    log.info("Red Parrot Accounting Ltd")
    log.info("Scan started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 70)

    start_time    = time.time()
    now_str       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    files_ok      = 0
    files_changed = 0
    files_missing = 0
    new_files     = 0
    alerts_raised = 0
    results       = []

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Step 1
    if progress_callback:
        progress_callback(1, "Step 1/4: Verifying baseline files...")
    log.info("Step 1/4: Verifying files in baseline database...")
    step1_ok, step1_changed, step1_missing, step1_alerts, step1_results = \
        _step_verify_baseline(cur, now_str)
    files_ok      += step1_ok
    files_changed += step1_changed
    files_missing += step1_missing
    alerts_raised += step1_alerts
    results.extend(step1_results)

    # Step 2
    if progress_callback:
        progress_callback(2, "Step 2/4: Scanning for new files...")
    log.info("Step 2/4: Scanning for new files not in baseline...")
    step2_count, step2_alerts, step2_results = \
        _step_detect_new_files(cur, now_str)
    new_files     += step2_count
    alerts_raised += step2_alerts
    results.extend(step2_results)

    # Step 3
    if progress_callback:
        progress_callback(3, "Step 3/4: Checking backup freshness...")
    log.info("Step 3/4: Checking backup freshness (age check)...")
    alerts_raised += _step_check_backup_age()

    # Step 4
    if progress_callback:
        progress_callback(4, "Step 4/4: Structural integrity check...")
    log.info("Step 4/4: Checking file integrity (open/parse test)...")
    step4_alerts, step4_results = _step_check_integrity(cur, now_str)
    alerts_raised += step4_alerts
    results.extend(step4_results)

    conn.commit()
    conn.close()

    total_scanned = files_ok + files_changed + files_missing + new_files
    duration      = round(time.time() - start_time, 2)

    # ── Size trend check ────────────────────────────────────────────────
    # Calculate total size of all currently OK files
    total_backup_size = _calculate_total_backup_size()
    prev_size         = get_previous_backup_size()

    if prev_size > 0 and total_backup_size > 0:
        drop_pct = ((prev_size - total_backup_size) / prev_size) * 100
        if drop_pct >= SIZE_DROP_ALERT_PERCENT:
            from utils.file_utils import format_size
            alert_msg = (
                f"Total backup size dropped by {drop_pct:.1f}% "
                f"(was {format_size(prev_size)}, now {format_size(total_backup_size)}). "
                f"Threshold: {SIZE_DROP_ALERT_PERCENT}%. "
                f"This may indicate bulk file deletion, ransomware activity, "
                f"or a failed backup job."
            )
            raise_alert("CRITICAL", "BACKUP SIZE DROP DETECTED", "ALL BACKUPS", alert_msg)
            alerts_raised += 1
            log.warning("Size drop alert: %.1f%% drop detected", drop_pct)
    # ────────────────────────────────────────────────────────────────────

    log.info("-" * 70)
    log.info("VERIFICATION COMPLETE")
    log.info("  Total files scanned  : %d", total_scanned)
    log.info("  Files OK             : %d", files_ok)
    log.info("  Files changed        : %d", files_changed)
    log.info("  Files missing        : %d", files_missing)
    log.info("  New files found      : %d", new_files)
    log.info("  Alerts raised        : %d", alerts_raised)
    log.info("  Duration             : %s seconds", duration)

    save_scan_run(
        now_str, total_scanned, files_ok, files_changed,
        files_missing, new_files, alerts_raised, duration,
        total_backup_size
    )

    if alerts_raised == 0:
        log.info("All backups verified successfully. No issues found.")
    else:
        log.warning("%d alert(s) raised.", alerts_raised)

    log.info("=" * 70)

    if progress_callback:
        progress_callback(5, f"Done — {total_scanned} files, {alerts_raised} alerts")

    # Auto-send digest if configured and time condition is met
    try:
        from core.digest import should_send_digest, send_digest
        if should_send_digest():
            log.info("Sending daily digest email...")
            send_digest()
    except Exception as e:
        log.warning("Digest send failed: %s", e)

    return results, alerts_raised


# =============================================================================
#   STEP FUNCTIONS
# =============================================================================

def _calculate_total_backup_size() -> int:
    """
    Sum the file_size of all OK files in the baseline.
    Used for size trend tracking — a sudden drop signals a problem.
    """
    if not os.path.exists(DB_PATH):
        return 0
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM file_hashes WHERE status='OK'"
        )
        total = cur.fetchone()[0]
        conn.close()
        return int(total)
    except Exception:
        return 0


def _step_verify_baseline(cur, now_str):
    cur.execute(
        "SELECT filepath, sha256, file_size, entropy "
        "FROM file_hashes WHERE status != 'MISSING'"
    )
    baseline_records = cur.fetchall()

    files_ok = files_changed = files_missing = alerts_raised = 0
    results  = []

    for (filepath, stored_hash, stored_size, stored_entropy) in baseline_records:
        if os.path.islink(filepath):
            continue

        if not os.path.exists(filepath):
            files_missing += 1
            alerts_raised += 1
            msg = "File no longer exists — deleted or moved"
            raise_alert("CRITICAL", "BACKUP FILE MISSING", filepath, msg)
            cur.execute(
                "UPDATE file_hashes SET status='MISSING', last_verified=? "
                "WHERE filepath=?",
                (now_str, filepath)
            )
            results.append({"filepath": filepath, "status": "MISSING",
                             "detail": msg, "severity": "CRITICAL"})
            continue

        current_hash    = calculate_sha256(filepath)
        current_size    = os.path.getsize(filepath)
        current_entropy = calculate_entropy(filepath)

        if current_hash is None:
            log.warning("Could not hash: %s — skipping", filepath)
            continue

        if current_hash != stored_hash:
            files_changed += 1
            alerts_raised += 1
            entropy_change = current_entropy - stored_entropy
            size_change    = current_size - stored_size

            if current_entropy > ENTROPY_SPIKE_THRESHOLD and entropy_change > 0.5:
                detail = (
                    f"HASH CHANGED + HIGH ENTROPY — possible ransomware encryption!\n"
                    f"  Old hash    : {stored_hash}\n"
                    f"  New hash    : {current_hash}\n"
                    f"  Old entropy : {stored_entropy}\n"
                    f"  New entropy : {current_entropy} "
                    f"(ABOVE {ENTROPY_SPIKE_THRESHOLD} threshold)\n"
                    f"  Size change : {format_size(size_change)} "
                    f"({'grew' if size_change > 0 else 'shrank'})"
                )
                raise_alert("CRITICAL", "RANSOMWARE SUSPECTED — BACKUP ENCRYPTED",
                            filepath, detail)
                sev = "CRITICAL"
            else:
                detail = (
                    f"File hash changed since baseline — "
                    f"possible tampering or unauthorised modification\n"
                    f"  Old hash    : {stored_hash}\n"
                    f"  New hash    : {current_hash}\n"
                    f"  Size change : {format_size(size_change)} "
                    f"({'grew' if size_change > 0 else 'shrank'})\n"
                    f"  Entropy     : {current_entropy}"
                )
                raise_alert("WARNING", "BACKUP FILE MODIFIED", filepath, detail)
                sev = "WARNING"

            cur.execute("""
                UPDATE file_hashes
                SET sha256=?, file_size=?, entropy=?, last_verified=?, status='CHANGED'
                WHERE filepath=?
            """, (current_hash, current_size, current_entropy, now_str, filepath))
            results.append({"filepath": filepath, "status": "CHANGED",
                             "detail": detail, "severity": sev})
        else:
            files_ok += 1
            cur.execute(
                "UPDATE file_hashes SET last_verified=?, status='OK' WHERE filepath=?",
                (now_str, filepath)
            )
            results.append({"filepath": filepath, "status": "OK",
                             "detail": "Hash verified — file intact", "severity": "OK"})

    return files_ok, files_changed, files_missing, alerts_raised, results


def _step_detect_new_files(cur, now_str):
    current_files = set(get_file_list(BACKUP_PATHS, MONITORED_EXTENSIONS))
    cur.execute("SELECT filepath FROM file_hashes")
    known_files   = set(row[0] for row in cur.fetchall())
    unknown_files = current_files - known_files

    count = alerts_raised = 0
    results = []

    ransom_keywords = [
        "readme", "decrypt", "restore", "how_to", "recover",
        "ransom", "!!!!", "your_files", "encrypted", "unlock"
    ]

    for filepath in unknown_files:
        count         += 1
        filename_lower = os.path.basename(filepath).lower()
        is_ransom_note = any(kw in filename_lower for kw in ransom_keywords)

        if is_ransom_note:
            alerts_raised += 1
            raise_alert(
                "CRITICAL", "POSSIBLE RANSOM NOTE DETECTED", filepath,
                f"New file with ransomware-associated name: "
                f"{os.path.basename(filepath)}"
            )
        else:
            log.info("  New file (not in baseline): %s", filepath)

        sha256    = calculate_sha256(filepath)
        entropy   = calculate_entropy(filepath)
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        modified  = (
            datetime.fromtimestamp(
                os.path.getmtime(filepath)
            ).strftime("%Y-%m-%d %H:%M:%S")
            if os.path.exists(filepath) else now_str
        )

        if sha256:
            cur.execute("""
                INSERT OR IGNORE INTO file_hashes
                    (filepath, sha256, file_size, entropy,
                     first_seen, last_verified, last_modified, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')
            """, (filepath, sha256, file_size, entropy,
                  now_str, now_str, modified))

        results.append({
            "filepath": filepath,
            "status":   "RANSOM NOTE!" if is_ransom_note else "NEW FILE",
            "detail":   "New file — added to baseline",
            "severity": "CRITICAL" if is_ransom_note else "INFO"
        })

    return count, alerts_raised, results


def _step_check_backup_age():
    alerts = 0
    for base_path in BACKUP_PATHS:
        if not os.path.exists(base_path):
            continue
        newest_time = newest_file = None
        for root, _, filenames in os.walk(base_path, followlinks=False):
            for filename in filenames:
                if MONITORED_EXTENSIONS:
                    if os.path.splitext(filename)[1].lower() \
                            not in MONITORED_EXTENSIONS:
                        continue
                filepath = os.path.join(root, filename)
                if os.path.islink(filepath):
                    continue
                try:
                    mtime = os.path.getmtime(filepath)
                    if newest_time is None or mtime > newest_time:
                        newest_time = mtime
                        newest_file = filepath
                except OSError:
                    continue

        if newest_time is None:
            raise_alert(
                "CRITICAL", "NO BACKUP FILES FOUND", base_path,
                "Backup folder exists but contains no monitored files — "
                "backup job may have failed"
            )
            alerts += 1
        else:
            age_hours = (time.time() - newest_time) / 3600
            if age_hours > MAX_BACKUP_AGE_HOURS:
                age_str = (
                    f"{age_hours:.1f} hours" if age_hours < 48
                    else f"{age_hours / 24:.1f} days"
                )
                raise_alert(
                    "WARNING", "STALE BACKUP DETECTED", base_path,
                    f"Newest backup is {age_str} old "
                    f"(threshold: {MAX_BACKUP_AGE_HOURS}h)\n"
                    f"Newest file: {newest_file}\n"
                    f"Backup job may have failed or been skipped."
                )
                alerts += 1
            else:
                log.info("  Backup freshness OK: %s (%.1fh old)",
                         base_path, age_hours)
    return alerts


def _step_check_integrity(cur, now_str):
    checkable_exts = {".zip", ".xlsx", ".xls", ".docx"}
    cur.execute("SELECT filepath FROM file_hashes WHERE status = 'OK'")
    ok_files = [row[0] for row in cur.fetchall()]

    checked = corrupt = alerts_raised = 0
    results = []

    for filepath in ok_files:
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in checkable_exts:
            continue
        if not os.path.exists(filepath) or os.path.islink(filepath):
            continue

        is_ok, msg = is_file_openable(filepath)
        checked   += 1

        if not is_ok:
            corrupt       += 1
            alerts_raised += 1
            raise_alert(
                "WARNING", "CORRUPT BACKUP FILE", filepath,
                f"File cannot be opened/parsed: {msg}\n"
                f"May be incomplete or damaged — test restore immediately."
            )
            cur.execute(
                "UPDATE file_hashes SET status='CORRUPT', last_verified=? "
                "WHERE filepath=?",
                (now_str, filepath)
            )
            results.append({"filepath": filepath, "status": "CORRUPT",
                             "detail": msg, "severity": "WARNING"})

    log.info("  Integrity check: %d files tested, %d corrupt", checked, corrupt)
    return alerts_raised, results

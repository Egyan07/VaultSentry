# =============================================================================
#   core/restore.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Restore engine — copies backup files back to a chosen destination,
#   preserving subfolder structure relative to the original backup root.
#
#   Design:
#     - get_restorable_files()  — query DB for files eligible for restore
#     - plan_restore()          — build a RestorePlan (dry-run preview)
#     - execute_restore()       — carry out the plan, return RestoreResult
#
#   The restore target is always chosen by the user via a GUI folder dialog.
#   Overwrite behaviour is handled by the caller (GUI prompts per-file).
# =============================================================================

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from logger import log
from config import DB_PATH, BACKUP_PATHS

import sqlite3


# =============================================================================
#   Data structures
# =============================================================================

@dataclass
class RestoreItem:
    """A single file selected for restore."""
    filepath:    str          # Original absolute path (on disk now)
    sha256:      str          # Baseline hash
    file_size:   int          # Size in bytes
    status:      str          # OK / CHANGED / MISSING / CORRUPT / NEW
    dest_path:   str = ""     # Computed destination path (filled by plan_restore)
    exists_at_dest: bool = False  # Whether dest_path already exists


@dataclass
class RestorePlan:
    """Preview of what a restore would do — shown before execution."""
    destination:   str
    items:         list[RestoreItem] = field(default_factory=list)
    total_size:    int = 0
    already_exist: int = 0    # Files that would be overwritten
    missing_src:   int = 0    # Files missing from source (cannot restore)


@dataclass
class RestoreResult:
    """Summary returned after execute_restore() completes."""
    restored:  int = 0
    skipped:   int = 0
    failed:    int = 0
    errors:    list[str] = field(default_factory=list)
    duration:  float = 0.0


# =============================================================================
#   Query
# =============================================================================

def get_restorable_files(status_filter: Optional[list[str]] = None) -> list[RestoreItem]:
    """
    Return all files from the baseline that match the given status filter.
    If status_filter is None or empty, return all files.

    status_filter examples: ["CHANGED"], ["MISSING", "CORRUPT"], None (all)
    """
    if not os.path.exists(DB_PATH):
        log.warning("restore: no database found at %s", DB_PATH)
        return []

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    if status_filter:
        placeholders = ",".join("?" * len(status_filter))
        cur.execute(
            f"SELECT filepath, sha256, file_size, status "
            f"FROM file_hashes WHERE status IN ({placeholders}) "
            f"ORDER BY status, filepath",
            status_filter
        )
    else:
        cur.execute(
            "SELECT filepath, sha256, file_size, status "
            "FROM file_hashes ORDER BY status, filepath"
        )

    rows = cur.fetchall()
    conn.close()

    return [
        RestoreItem(
            filepath=row[0],
            sha256=row[1],
            file_size=row[2] or 0,
            status=row[3],
        )
        for row in rows
    ]


# =============================================================================
#   Plan (dry-run)
# =============================================================================

def plan_restore(items: list[RestoreItem], destination: str) -> RestorePlan:
    """
    Build a RestorePlan without touching any files.
    Computes destination paths and checks for conflicts.

    Destination path logic:
      Strip the longest matching BACKUP_PATH prefix from each filepath,
      then join the remainder onto destination.

      Example:
        filepath    = D:\\Backups\\ClientA\\2026\\data.zip
        backup root = D:\\Backups
        dest        = C:\\Restore
        dest_path   = C:\\Restore\\ClientA\\2026\\data.zip
    """
    plan = RestorePlan(destination=destination)

    for item in items:
        rel = _relative_to_backup_root(item.filepath)
        dest_path = os.path.join(destination, rel)

        item.dest_path      = dest_path
        item.exists_at_dest = os.path.exists(dest_path)

        plan.items.append(item)
        plan.total_size += item.file_size

        if not os.path.exists(item.filepath):
            plan.missing_src += 1
        if item.exists_at_dest:
            plan.already_exist += 1

    return plan


# =============================================================================
#   Execute
# =============================================================================

def execute_restore(
    plan:           RestorePlan,
    overwrite_all:  bool = False,
    skip_existing:  bool = False,
    overwrite_set:  Optional[set] = None,
    progress_callback=None,
) -> RestoreResult:
    """
    Execute a RestorePlan.

    overwrite_all    — overwrite every existing file without asking
    skip_existing    — skip every file that already exists at destination
    overwrite_set    — set of dest_paths the user explicitly approved to overwrite
    progress_callback(current, total, filepath) — GUI progress hook
    """
    result = RestoreResult()
    start  = datetime.now()
    total  = len(plan.items)

    for idx, item in enumerate(plan.items):
        if progress_callback:
            progress_callback(idx + 1, total, item.filepath)

        # Cannot restore a file that doesn't exist at source
        if not os.path.exists(item.filepath):
            result.failed += 1
            result.errors.append(
                f"Source not found: {item.filepath}"
            )
            log.warning("restore: source missing — %s", item.filepath)
            continue

        # Handle existing destination
        if item.exists_at_dest:
            if skip_existing:
                result.skipped += 1
                log.info("restore: skipped (exists) — %s", item.dest_path)
                continue
            if not overwrite_all:
                if overwrite_set is None or item.dest_path not in overwrite_set:
                    result.skipped += 1
                    log.info("restore: skipped (not approved) — %s", item.dest_path)
                    continue

        # Create destination subfolder tree
        try:
            os.makedirs(os.path.dirname(item.dest_path), exist_ok=True)
        except OSError as e:
            result.failed += 1
            result.errors.append(f"Cannot create folder for {item.dest_path}: {e}")
            continue

        # Copy
        try:
            shutil.copy2(item.filepath, item.dest_path)
            result.restored += 1
            log.info("restore: copied %s → %s", item.filepath, item.dest_path)
        except Exception as e:
            result.failed += 1
            result.errors.append(f"Failed to copy {item.filepath}: {e}")
            log.error("restore: failed %s — %s", item.filepath, e)

    result.duration = (datetime.now() - start).total_seconds()

    log.info(
        "Restore complete — %d restored, %d skipped, %d failed in %.1fs",
        result.restored, result.skipped, result.failed, result.duration
    )
    return result


# =============================================================================
#   Helpers
# =============================================================================

def _relative_to_backup_root(filepath: str) -> str:
    """
    Strip the longest matching BACKUP_PATH prefix from filepath.
    Returns the relative remainder, or just the filename if no match found.

    Example:
      filepath    = D:\\Backups\\ClientA\\data.zip
      BACKUP_PATHS = ["D:\\Backups"]
      returns      ClientA\\data.zip
    """
    fp_norm = os.path.normpath(filepath)

    best_match = ""
    for root in BACKUP_PATHS:
        root_norm = os.path.normpath(root)
        if fp_norm.startswith(root_norm + os.sep) or fp_norm == root_norm:
            if len(root_norm) > len(best_match):
                best_match = root_norm

    if best_match:
        rel = os.path.relpath(fp_norm, best_match)
        return rel

    # Fallback — use just the filename
    return os.path.basename(filepath)

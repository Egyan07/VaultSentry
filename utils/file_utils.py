# =============================================================================
#   utils/file_utils.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Pure utility functions: hashing, entropy, file walking, size formatting.
#   No side effects — nothing here writes to disk, DB, or sends alerts.
# =============================================================================

import os
import math
import hashlib
import zipfile

from logger import log

try:
    import openpyxl
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


def calculate_sha256(filepath: str) -> str | None:
    """
    Hash a file in 64 KB chunks using SHA-256.
    Returns hex string, or None if the file cannot be read.
    """
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (PermissionError, FileNotFoundError, OSError) as e:
        log.warning("Cannot hash %s: %s", filepath, e)
        return None


def calculate_entropy(filepath: str) -> float:
    """
    Calculate Shannon entropy of a file (0.0 – 8.0).
    Reads up to 1 MB for performance. High entropy (>7.5) suggests encryption.
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read(1_000_000)
        if not data:
            return 0.0
        frequency = [0] * 256
        for byte in data:
            frequency[byte] += 1
        length  = len(data)
        entropy = 0.0
        for count in frequency:
            if count > 0:
                prob     = count / length
                entropy -= prob * math.log2(prob)
        return round(entropy, 4)
    except (PermissionError, FileNotFoundError, OSError):
        return 0.0


def is_file_openable(filepath: str) -> tuple[bool, str]:
    """
    Structurally validate a file to detect silent corruption.
    Supports .zip, .xlsx, .xls, .docx — falls back to size check for others.
    Returns (is_ok, message).
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".zip":
            with zipfile.ZipFile(filepath, "r") as z:
                bad = z.testzip()
                if bad:
                    return False, f"Corrupt entry inside zip: {bad}"
            return True, "ZIP integrity OK"

        elif ext in (".xlsx", ".xls", ".docx"):
            if EXCEL_AVAILABLE and ext == ".xlsx":
                openpyxl.load_workbook(filepath, read_only=True, data_only=True)
                return True, "Excel file opens OK"
            else:
                with open(filepath, "rb") as f:
                    magic = f.read(2)
                if magic == b"PK":
                    return True, "Office file header OK"
                return False, "Office file header invalid (not PK)"

        else:
            size = os.path.getsize(filepath)
            if size == 0:
                return False, "File is empty (0 bytes)"
            return True, "File readable"

    except zipfile.BadZipFile:
        return False, "Bad ZIP — corrupt or encrypted"
    except Exception as e:
        return False, f"Cannot open: {e}"


def get_file_list(paths: list[str], extensions: list[str]) -> list[str]:
    """
    Walk backup paths and return a list of real file paths.
    Skips symlinks and hidden directories.
    """
    files = []
    for base_path in paths:
        if not os.path.exists(base_path):
            log.warning("Backup path does not exist: %s", base_path)
            continue
        for root, dirs, filenames in os.walk(base_path, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in filenames:
                filepath = os.path.join(root, filename)
                if os.path.islink(filepath):
                    continue
                if extensions:
                    if os.path.splitext(filename)[1].lower() not in extensions:
                        continue
                files.append(filepath)
    return files


def format_size(size_bytes: int) -> str:
    """Human-readable file size. Safe for zero and negative inputs."""
    size_bytes = abs(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

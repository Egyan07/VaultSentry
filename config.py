# =============================================================================
#   config.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   All user-editable configuration lives here.
#   Edit this file before first run.
# =============================================================================

import os

APP_NAME    = "VaultSentry"
APP_VERSION = "1.0.1"

# Paths to monitor for backup files (add as many as needed)
BACKUP_PATHS = [
    r"C:\Backups",
    r"D:\Backups",
    # r"\\SERVER\Backups",       # Uncomment for network shares
    # r"E:\ClientDataBackup",    # Uncomment for external drives
]

# File extensions to monitor (leave empty list [] to monitor ALL files)
MONITORED_EXTENSIONS = [
    ".zip", ".bak", ".sql", ".xlsx", ".xls",
    ".docx", ".pdf", ".tar", ".gz", ".7z", ".rar",
]

# Alert if backup folder has no monitored files newer than this many hours
MAX_BACKUP_AGE_HOURS = 25

# Alert if a backup file's entropy spikes above this (ransomware indicator)
# Normal files: 4.0–6.5 | Encrypted/compressed: 7.5–8.0
ENTROPY_SPIKE_THRESHOLD = 7.8

# File extensions excluded from entropy-based ransomware detection.
# These formats are inherently high-entropy (compressed or structured binary)
# so a high entropy score alone is NOT a reliable ransomware indicator for them.
# Hash-change alerts still fire normally — only the "RANSOMWARE SUSPECTED"
# entropy-spike escalation is skipped. Structural integrity (is_file_openable)
# provides the second layer of protection for these formats.
ENTROPY_EXCLUDE_EXTENSIONS = {
    ".zip", ".gz", ".7z", ".rar", ".tar",   # already compressed
    ".pdf",                                   # typically >7.0 entropy by design
    ".xlsx", ".xls", ".docx",               # ZIP-based Office formats
}

# Alert if backup total size drops by more than this percentage
SIZE_DROP_ALERT_PERCENT = 30

# Alert deduplication — suppress repeat alerts for the same file within N hours
ALERT_COOLDOWN_HOURS = 24

# Admin machine name for msg.exe popup alerts
ADMIN_PC = "ADMINPC"

# Email settings
# SECURITY: Do NOT put your password here. Set it as a Windows environment
# variable:
#   PowerShell (run as Administrator):
#     [System.Environment]::SetEnvironmentVariable(
#       'VAULTSENTRY_EMAIL_PASSWORD', 'your_app_password', 'Machine')
EMAIL_ENABLED     = False
EMAIL_FROM        = "vaultsentry@redparrot.co.uk"
EMAIL_TO          = "admin@redparrot.co.uk"
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT   = 587

# Daily digest email
# When DIGEST_ENABLED = True, a summary email is sent once per day after the
# nightly verify run (instead of individual per-alert emails for every issue).
# DIGEST_TIME is the hour (24h) after which the digest is sent — set this to
# match your scheduled verify time (e.g. 2 = send after the 02:00 AM run).
# Individual CRITICAL alerts still fire immediately regardless of this setting.
DIGEST_ENABLED    = False
DIGEST_TIME       = 8     # Send digest after this hour (0-23)

# Storage paths — change only if necessary
LOG_DIR    = r"C:\SecurityLogs\VaultSentry"
DB_PATH    = os.path.join(LOG_DIR, "vaultsentry.db")
LOG_FILE   = os.path.join(LOG_DIR, "vaultsentry.log")
REPORT_DIR = os.path.join(LOG_DIR, "Reports")

# =============================================================================
#   logger.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import os
import logging
from logging.handlers import RotatingFileHandler

from config import LOG_DIR, LOG_FILE, APP_NAME

os.makedirs(LOG_DIR, exist_ok=True)

log = logging.getLogger(APP_NAME)
log.setLevel(logging.DEBUG)

if not log.handlers:
    # File handler — 5 MB max, 3 backups
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3,
                             encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    log.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    ))
    log.addHandler(ch)

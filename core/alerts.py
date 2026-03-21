# =============================================================================
#   core/alerts.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Central alert dispatcher.
#   Fixes applied:
#     - starttls() now uses ssl.create_default_context() — no MITM risk
#     - Alert deduplication via ALERT_COOLDOWN_HOURS — no nightly spam
# =============================================================================

import os
import ssl
import smtplib
import threading
import subprocess
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import (
    APP_NAME, APP_VERSION, ADMIN_PC,
    EMAIL_ENABLED, EMAIL_FROM, EMAIL_TO,
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
)
from logger import log
from core.database import save_alert, is_alert_duplicate, set_setting

try:
    import tkinter as tk
    from tkinter import messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False


def raise_alert(severity: str, alert_type: str, filepath: str, details: str):
    """
    Central alert dispatcher.

    - Checks deduplication: skips if same alert was raised within cooldown window
    - Logs to file
    - Saves to database
    - Fires non-blocking desktop popup
    - Sends msg.exe to ADMIN_PC
    - Optionally sends email (with proper TLS verification)

    severity: 'CRITICAL' | 'WARNING' | 'INFO'
    """
    # Deduplication check — suppress repeat alerts for the same issue
    if is_alert_duplicate(alert_type, filepath):
        log.debug("Alert suppressed (cooldown): %s — %s", alert_type, filepath)
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message   = (
        f"[{APP_NAME}]\n"
        f"Severity  : {severity}\n"
        f"Alert     : {alert_type}\n"
        f"File      : {filepath}\n"
        f"Details   : {details}\n"
        f"Time      : {timestamp}\n"
        f"Red Parrot Accounting Ltd"
    )

    log.warning("ALERT [%s] %s — %s — %s", severity, alert_type, filepath, details)

    save_alert(timestamp, severity, alert_type, filepath, details)
    _send_popup(severity, message)
    _send_msg_exe(severity, alert_type, filepath)

    if EMAIL_ENABLED:
        try:
            _send_email(severity, alert_type, message)
            # Clear any previous failure flag on success
            set_setting("email_failure", "")
        except Exception as e:
            err_msg = str(e)
            log.error("Email alert failed: %s", err_msg)
            # FIX: persist failure so Dashboard can show a visible warning banner
            set_setting("email_failure", err_msg)


# =============================================================================
#   Private helpers
# =============================================================================

def _send_popup(severity: str, message: str):
    """Non-blocking desktop popup via daemon thread."""
    if not TKINTER_AVAILABLE:
        return
    try:
        t = threading.Thread(
            target=_show_popup_worker, args=(severity, message), daemon=True
        )
        t.start()
    except Exception:
        pass


def _show_popup_worker(severity: str, message: str):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        title = f"{APP_NAME} v{APP_VERSION} — {severity}"
        messagebox.showwarning(title=title, message=message, parent=root)
        root.destroy()
    except Exception:
        pass


def _send_msg_exe(severity: str, alert_type: str, filepath: str):
    try:
        short_msg = (
            f"{APP_NAME} [{severity}]: {alert_type} — "
            f"{os.path.basename(filepath)}"
        )
        subprocess.run(
            ["msg", ADMIN_PC, short_msg],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


def _get_email_password() -> str:
    """Read email password from env var. Never hardcode credentials."""
    pwd = os.environ.get("VAULTSENTRY_EMAIL_PASSWORD", "")
    if not pwd:
        log.warning(
            "EMAIL_ENABLED is True but VAULTSENTRY_EMAIL_PASSWORD env var "
            "is not set. Email alert skipped."
        )
    return pwd


def _send_email(severity: str, subject_suffix: str, body: str):
    password = _get_email_password()
    if not password:
        return

    msg            = MIMEMultipart()
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg["Subject"] = f"[{APP_NAME}] {severity}: {subject_suffix}"
    msg.attach(MIMEText(body, "plain"))

    # FIX: ssl.create_default_context() enforces certificate verification
    context = ssl.create_default_context()
    with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(EMAIL_FROM, password)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    log.info("Email alert sent to %s", EMAIL_TO)

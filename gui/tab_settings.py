# =============================================================================
#   gui/tab_settings.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess, sys, os

from gui.theme import *
from config import (
    BACKUP_PATHS, MONITORED_EXTENSIONS, MAX_BACKUP_AGE_HOURS,
    ENTROPY_SPIKE_THRESHOLD, ALERT_COOLDOWN_HOURS,
    ADMIN_PC, EMAIL_ENABLED, EMAIL_FROM, EMAIL_TO,
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
    LOG_DIR, DB_PATH, LOG_FILE, REPORT_DIR, APP_NAME, APP_VERSION,
)


class SettingsTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, padx=20, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Settings & Info", font=FONT_H1,
                 fg=ACCENT, bg=BG_PANEL).pack(side="left")

        # Scrollable area
        canvas = tk.Canvas(self, bg=BG_DARK, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG_DARK)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(e):
            canvas.itemconfig(inner_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        self._build_inner(inner)

    def _build_inner(self, parent):
        pad = {"padx": 24, "pady": 6}

        def section(title):
            f = tk.Frame(parent, bg=BG_CARD, padx=16, pady=10)
            f.pack(fill="x", padx=20, pady=(12, 0))
            tk.Label(f, text=title, font=FONT_H2,
                     fg=ACCENT, bg=BG_CARD).pack(anchor="w", pady=(0, 6))
            return f

        def row(frame, label, value, color=None):
            r = tk.Frame(frame, bg=BG_CARD)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, font=FONT_BODY, fg=TEXT_SECONDARY,
                     bg=BG_CARD, width=28, anchor="w").pack(side="left")
            tk.Label(r, text=str(value), font=FONT_MONO,
                     fg=color or TEXT_PRIMARY, bg=BG_CARD,
                     anchor="w", wraplength=500).pack(side="left")

        # Version info
        f = section("About VaultSentry")
        row(f, "Version",        f"{APP_NAME} v{APP_VERSION}")
        row(f, "Author",         "Egyan")
        row(f, "Organisation",   "Red Parrot Accounting Ltd")
        row(f, "Purpose",        "Backup integrity monitoring — SHA-256 + entropy analysis")

        # Backup paths
        f = section("Backup Paths")
        for p in BACKUP_PATHS:
            row(f, "Monitored path", p,
                color=OK_COLOR if os.path.exists(p) else CRITICAL_COLOR)
        if BACKUP_PATHS:
            any_exists = any(os.path.exists(p) for p in BACKUP_PATHS)
            status = "✓ At least one path exists" if any_exists else "✗ No paths found — check config.py"
            row(f, "Status", status,
                color=OK_COLOR if any_exists else CRITICAL_COLOR)

        # Scan config
        f = section("Scan Configuration")
        row(f, "File extensions",       ", ".join(MONITORED_EXTENSIONS) or "ALL files")
        row(f, "Max backup age",         f"{MAX_BACKUP_AGE_HOURS} hours")
        row(f, "Entropy threshold",      f"{ENTROPY_SPIKE_THRESHOLD} (ransomware indicator)")
        row(f, "Alert cooldown",         f"{ALERT_COOLDOWN_HOURS} hours")

        # Alert config
        f = section("Alert Configuration")
        row(f, "Admin PC",               ADMIN_PC)
        row(f, "Email alerts",           "Enabled" if EMAIL_ENABLED else "Disabled",
            color=OK_COLOR if EMAIL_ENABLED else TEXT_MUTED)
        if EMAIL_ENABLED:
            row(f, "Email from",         EMAIL_FROM)
            row(f, "Email to",           EMAIL_TO)
            row(f, "SMTP server",        f"{EMAIL_SMTP_SERVER}:{EMAIL_SMTP_PORT}")
            pwd_set = bool(os.environ.get("VAULTSENTRY_EMAIL_PASSWORD"))
            row(f, "Email password",
                "✓ Set via environment variable" if pwd_set else "✗ Not set (alerts will fail)",
                color=OK_COLOR if pwd_set else CRITICAL_COLOR)

        # Storage paths
        f = section("Storage Paths")
        row(f, "Log directory",    LOG_DIR)
        row(f, "Database",         DB_PATH)
        row(f, "Log file",         LOG_FILE)
        row(f, "Reports",          REPORT_DIR)

        # Quick actions
        f = section("Quick Actions")

        btn_frame = tk.Frame(f, bg=BG_CARD)
        btn_frame.pack(anchor="w", pady=4)

        def open_config():
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
            try:
                os.startfile(os.path.abspath(config_path))
            except Exception as e:
                messagebox.showerror("Error", f"Could not open config.py:\n{e}")

        def open_log():
            try:
                os.startfile(LOG_FILE)
            except Exception as e:
                messagebox.showerror("Error", f"Could not open log file:\n{e}")

        def open_log_dir():
            os.makedirs(LOG_DIR, exist_ok=True)
            os.startfile(LOG_DIR)

        for text, cmd in [
            ("📝  Edit config.py",     open_config),
            ("📄  View Log File",       open_log),
            ("📁  Open Log Folder",     open_log_dir),
        ]:
            tk.Button(
                btn_frame, text=text, font=FONT_BODY,
                bg=ACCENT_DIM, fg=TEXT_PRIMARY,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", padx=14, pady=6, cursor="hand2",
                command=cmd
            ).pack(side="left", padx=(0, 10))

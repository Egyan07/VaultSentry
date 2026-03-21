# =============================================================================
#   gui/tab_dashboard.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from gui.theme import *
from core.database import get_stats, get_size_trend, get_setting
from utils.file_utils import format_size


class DashboardTab(tk.Frame):
    def __init__(self, parent, on_baseline, on_verify, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._on_baseline = on_baseline
        self._on_verify   = on_verify
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, padx=20, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="VaultSentry", font=FONT_TITLE,
                 fg=ACCENT, bg=BG_PANEL).pack(side="left")
        tk.Label(hdr, text="  Backup Integrity Monitor — Red Parrot Accounting Ltd",
                 font=FONT_BODY, fg=TEXT_SECONDARY, bg=BG_PANEL).pack(side="left")

        self._ts_label = tk.Label(hdr, text="", font=FONT_SMALL,
                                   fg=TEXT_MUTED, bg=BG_PANEL)
        self._ts_label.pack(side="right")

        # FIX: Email failure banner — visible when alert emails are failing
        # Hidden by default; shown only when core/alerts.py records a failure
        self._email_fail_var    = tk.StringVar(value="")
        self._email_fail_banner = tk.Label(
            self, textvariable=self._email_fail_var,
            font=FONT_BODY, fg="#ff4444", bg="#3a0a0a",
            padx=16, pady=6, anchor="w"
        )
        # Banner is packed/unpacked dynamically by refresh_stats()

        # Stat cards row
        cards_frame = tk.Frame(self, bg=BG_DARK, pady=16)
        cards_frame.pack(fill="x", padx=20)

        self._stat_vars = {}
        stats_def = [
            ("total",   "Total Files",    TEXT_PRIMARY),
            ("ok",      "Files OK",       OK_COLOR),
            ("changed", "Changed",        WARNING_COLOR),
            ("missing", "Missing",        CRITICAL_COLOR),
            ("corrupt", "Corrupt",        CRITICAL_COLOR),
            ("new",     "New Files",      INFO_COLOR),
        ]
        for col, (key, label, color) in enumerate(stats_def):
            card = tk.Frame(cards_frame, bg=BG_CARD, padx=16, pady=14,
                            relief="flat", bd=0)
            card.grid(row=0, column=col, padx=6, sticky="nsew")
            cards_frame.columnconfigure(col, weight=1)

            var = tk.StringVar(value="—")
            self._stat_vars[key] = var

            tk.Label(card, textvariable=var, font=("Consolas", 22, "bold"),
                     fg=color, bg=BG_CARD).pack()
            tk.Label(card, text=label, font=FONT_SMALL,
                     fg=TEXT_SECONDARY, bg=BG_CARD).pack()

        # Alert summary cards
        alert_frame = tk.Frame(self, bg=BG_DARK, pady=4)
        alert_frame.pack(fill="x", padx=20)

        for col, (key, label, color) in enumerate([
            ("crit_alerts", "Critical Alerts (all time)", CRITICAL_COLOR),
            ("warn_alerts", "Warning Alerts (all time)",  WARNING_COLOR),
        ]):
            card = tk.Frame(alert_frame, bg=BG_CARD, padx=16, pady=10)
            card.grid(row=0, column=col, padx=6, sticky="nsew")
            alert_frame.columnconfigure(col, weight=1)

            var = tk.StringVar(value="—")
            self._stat_vars[key] = var
            tk.Label(card, textvariable=var, font=("Consolas", 18, "bold"),
                     fg=color, bg=BG_CARD).pack()
            tk.Label(card, text=label, font=FONT_SMALL,
                     fg=TEXT_SECONDARY, bg=BG_CARD).pack()

        # Last scan info
        info_frame = tk.Frame(self, bg=BG_CARD, padx=20, pady=10)
        info_frame.pack(fill="x", padx=20, pady=(10, 0))
        self._last_scan_var = tk.StringVar(value="Last scan: No scans run yet")
        tk.Label(info_frame, textvariable=self._last_scan_var, font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_CARD).pack(side="left")

        # Action buttons
        btn_frame = tk.Frame(self, bg=BG_DARK, pady=16)
        btn_frame.pack(fill="x", padx=20)

        self._progress_var = tk.StringVar(value="")
        self._progress_bar = ttk.Progressbar(btn_frame, mode="indeterminate",
                                              length=300)

        btn_style = {"font": FONT_H2, "relief": "flat", "bd": 0,
                     "padx": 20, "pady": 10, "cursor": "hand2"}

        baseline_btn = tk.Button(
            btn_frame, text="⬛  Create Baseline",
            bg=ACCENT_DIM, fg=TEXT_PRIMARY,
            activebackground=ACCENT, activeforeground="white",
            command=self._on_baseline, **btn_style
        )
        baseline_btn.pack(side="left", padx=(0, 10))

        verify_btn = tk.Button(
            btn_frame, text="🔍  Run Verification",
            bg="#1a4a2a", fg=OK_COLOR,
            activebackground="#1e5a34", activeforeground=OK_COLOR,
            command=self._on_verify, **btn_style
        )
        verify_btn.pack(side="left", padx=(0, 10))

        self._status_label = tk.Label(btn_frame, textvariable=self._progress_var,
                                       font=FONT_BODY, fg=TEXT_SECONDARY,
                                       bg=BG_DARK)
        self._status_label.pack(side="left", padx=10)

        # Size trend bar
        trend_frame = tk.Frame(self, bg=BG_CARD, padx=20, pady=10)
        trend_frame.pack(fill="x", padx=20, pady=(8, 0))

        tk.Label(trend_frame, text="Backup Size Trend (last 14 runs)",
                 font=FONT_H2, fg=TEXT_SECONDARY, bg=BG_CARD).pack(anchor="w")

        self._trend_canvas = tk.Canvas(trend_frame, bg=BG_CARD,
                                        height=60, highlightthickness=0)
        self._trend_canvas.pack(fill="x", pady=(4, 0))

        # Log console
        log_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=8)
        log_frame.pack(fill="both", expand=True)

        tk.Label(log_frame, text="Live Log", font=FONT_H2,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(anchor="w")

        console_frame = tk.Frame(log_frame, bg=BG_CARD)
        console_frame.pack(fill="both", expand=True, pady=(4, 0))

        scrollbar = tk.Scrollbar(console_frame)
        scrollbar.pack(side="right", fill="y")

        self._console = tk.Text(
            console_frame, bg="#0a1520", fg=TEXT_PRIMARY,
            font=FONT_MONO, relief="flat", bd=0,
            state="disabled", wrap="word",
            yscrollcommand=scrollbar.set
        )
        self._console.pack(fill="both", expand=True, padx=2, pady=2)
        scrollbar.config(command=self._console.yview)

        # Colour tags for log lines
        self._console.tag_configure("critical", foreground=CRITICAL_COLOR)
        self._console.tag_configure("warning",  foreground=WARNING_COLOR)
        self._console.tag_configure("ok",       foreground=OK_COLOR)
        self._console.tag_configure("info",     foreground=INFO_COLOR)
        self._console.tag_configure("muted",    foreground=TEXT_MUTED)

        self.refresh_stats()

    def refresh_stats(self):
        stats = get_stats()
        for key, var in self._stat_vars.items():
            var.set(str(stats.get(key, "—")))

        last = stats.get("last_run")
        if last:
            self._last_scan_var.set(
                f"Last scan: {last[0]}   |   {last[1]} files   |   {last[2]}s"
            )

        now = datetime.now().strftime("%H:%M:%S")
        self._ts_label.config(text=f"Refreshed {now}")

        # FIX: Show/hide email failure banner based on persisted failure flag
        email_failure = get_setting("email_failure", "")
        if email_failure:
            self._email_fail_var.set(
                f"  \u26a0  Email alerts failing — {email_failure[:120]}"
            )
            self._email_fail_banner.pack(fill="x", after=self.winfo_children()[0])
        else:
            self._email_fail_banner.pack_forget()

        self._draw_trend()

    def _draw_trend(self):
        """Draw a simple bar sparkline of backup size over the last N runs."""
        canvas = self._trend_canvas
        canvas.delete("all")
        canvas.update_idletasks()

        trend = get_size_trend(14)
        if not trend:
            canvas.create_text(
                10, 30, text="No scan history yet — run a verification first",
                fill=TEXT_MUTED, font=FONT_SMALL, anchor="w"
            )
            return

        w      = canvas.winfo_width() or 600
        h      = canvas.winfo_height() or 60
        n      = len(trend)
        max_sz = max(r["total_backup_size"] for r in trend) or 1
        bar_w  = max(4, (w - 40) // n - 2)
        pad_l  = 10
        pad_b  = 8
        bar_h  = h - pad_b - 14

        for i, run in enumerate(trend):
            size   = run["total_backup_size"]
            height = max(2, int((size / max_sz) * bar_h))
            x1     = pad_l + i * (bar_w + 2)
            x2     = x1 + bar_w
            y1     = h - pad_b - height
            y2     = h - pad_b

            # Colour: last bar is accent, rest are dim
            color = ACCENT if i == n - 1 else ACCENT_DIM

            # Check for drop vs previous
            if i > 0 and max_sz > 0:
                prev = trend[i - 1]["total_backup_size"]
                if prev > 0:
                    drop = (prev - size) / prev * 100
                    if drop >= 30:
                        color = CRITICAL_COLOR

            canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")

            # Label last bar with size
            if i == n - 1:
                canvas.create_text(
                    x1 + bar_w // 2, y1 - 2,
                    text=format_size(size),
                    fill=TEXT_SECONDARY, font=FONT_SMALL, anchor="s"
                )

    def log_line(self, text: str, level: str = "info"):
        self._console.config(state="normal")
        tag = level.lower() if level.lower() in ("critical", "warning", "ok", "info", "muted") else "info"
        self._console.insert("end", text + "\n", tag)
        self._console.see("end")
        self._console.config(state="disabled")

    def set_status(self, text: str):
        self._progress_var.set(text)

    def start_progress(self):
        self._progress_bar.pack(side="left", padx=10)
        self._progress_bar.start(12)

    def stop_progress(self):
        self._progress_bar.stop()
        self._progress_bar.pack_forget()

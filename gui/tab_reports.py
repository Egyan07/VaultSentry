# =============================================================================
#   gui/tab_reports.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import os
import threading
import tkinter as tk
from tkinter import messagebox

from gui.theme import *
from core.reports import generate_excel_report
from config import REPORT_DIR


class ReportsTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, padx=20, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Reports", font=FONT_H1,
                 fg=ACCENT, bg=BG_PANEL).pack(side="left")

        # Generate button
        btn_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=20)
        btn_frame.pack(fill="x")

        gen_btn = tk.Button(
            btn_frame, text="📊  Generate Excel Report",
            font=FONT_H2, bg=ACCENT_DIM, fg=TEXT_PRIMARY,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", padx=20, pady=10, cursor="hand2",
            command=self._generate
        )
        gen_btn.pack(side="left")

        open_btn = tk.Button(
            btn_frame, text="📁  Open Reports Folder",
            font=FONT_H2, bg=BG_CARD, fg=TEXT_SECONDARY,
            activebackground=BG_HOVER, activeforeground=TEXT_PRIMARY,
            relief="flat", padx=20, pady=10, cursor="hand2",
            command=self._open_folder
        )
        open_btn.pack(side="left", padx=12)

        self._status_var = tk.StringVar(value="")
        tk.Label(btn_frame, textvariable=self._status_var, font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(side="left", padx=12)

        # Info card
        info = tk.Frame(self, bg=BG_CARD, padx=20, pady=16)
        info.pack(fill="x", padx=20, pady=(0, 12))

        info_text = (
            "Reports are generated as colour-coded Excel files with three sheets:\n\n"
            "  •  Scan Results  — every file checked, status, and details\n"
            "  •  Summary       — counts at a glance: OK, Changed, Missing, Corrupt\n"
            "  •  Alert History — all alerts ever raised\n\n"
            f"Saved to:  {REPORT_DIR}\n"
            "Also auto-copied to your Downloads folder."
        )
        tk.Label(info, text=info_text, font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_CARD,
                 justify="left", anchor="w").pack(anchor="w")

        # Previous reports list
        list_frame = tk.Frame(self, bg=BG_DARK, padx=20)
        list_frame.pack(fill="both", expand=True)

        tk.Label(list_frame, text="Previous Reports", font=FONT_H2,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(anchor="w", pady=(8, 4))

        self._listbox = tk.Listbox(
            list_frame, bg=BG_CARD, fg=TEXT_PRIMARY,
            font=FONT_MONO, relief="flat", bd=0,
            selectbackground=ACCENT_DIM, activestyle="none"
        )
        self._listbox.pack(fill="both", expand=True)
        self._refresh_list()

    def _generate(self):
        self._status_var.set("Generating...")

        def run():
            path = generate_excel_report()
            if path:
                self.after(0, lambda: self._status_var.set(
                    f"Saved: {os.path.basename(path)}"))
                self.after(0, self._refresh_list)
            else:
                self.after(0, lambda: self._status_var.set(
                    "Failed — install openpyxl: pip install openpyxl"))

        threading.Thread(target=run, daemon=True).start()

    def _open_folder(self):
        os.makedirs(REPORT_DIR, exist_ok=True)
        os.startfile(REPORT_DIR)

    def _refresh_list(self):
        self._listbox.delete(0, "end")
        if not os.path.exists(REPORT_DIR):
            return
        files = sorted(
            [f for f in os.listdir(REPORT_DIR) if f.endswith(".xlsx")],
            reverse=True
        )
        for f in files:
            self._listbox.insert("end", f)

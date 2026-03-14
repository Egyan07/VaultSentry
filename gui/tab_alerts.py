# =============================================================================
#   gui/tab_alerts.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
# =============================================================================

import tkinter as tk
from tkinter import ttk

from gui.theme import *
from core.database import get_recent_alerts


class AlertsTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._build()

    def _build(self):
        # Header bar
        hdr = tk.Frame(self, bg=BG_PANEL, padx=20, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Alert History", font=FONT_H1,
                 fg=ACCENT, bg=BG_PANEL).pack(side="left")

        refresh_btn = tk.Button(
            hdr, text="↻  Refresh", font=FONT_BODY,
            bg=ACCENT_DIM, fg=TEXT_PRIMARY,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self.refresh
        )
        refresh_btn.pack(side="right")

        # Filter row
        filter_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=8)
        filter_frame.pack(fill="x")

        tk.Label(filter_frame, text="Filter:", font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(side="left")

        self._filter_var = tk.StringVar(value="ALL")
        for label, value in [("All", "ALL"), ("Critical", "CRITICAL"),
                               ("Warning", "WARNING"), ("Info", "INFO")]:
            rb = tk.Radiobutton(
                filter_frame, text=label, variable=self._filter_var,
                value=value, font=FONT_BODY, fg=TEXT_SECONDARY,
                bg=BG_DARK, selectcolor=BG_CARD, activebackground=BG_DARK,
                command=self.refresh
            )
            rb.pack(side="left", padx=8)

        self._count_var = tk.StringVar(value="")
        tk.Label(filter_frame, textvariable=self._count_var, font=FONT_SMALL,
                 fg=TEXT_MUTED, bg=BG_DARK).pack(side="right")

        # Treeview
        tree_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=4)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("VS.Treeview",
                         background=BG_CARD, foreground=TEXT_PRIMARY,
                         fieldbackground=BG_CARD, rowheight=22,
                         font=FONT_MONO)
        style.configure("VS.Treeview.Heading",
                         background=BG_PANEL, foreground=TEXT_PRIMARY,
                         font=FONT_H2, relief="flat")
        style.map("VS.Treeview",
                  background=[("selected", ACCENT_DIM)],
                  foreground=[("selected", "white")])

        columns = ("timestamp", "severity", "alert_type", "filepath")
        self._tree = ttk.Treeview(tree_frame, columns=columns,
                                   show="headings", style="VS.Treeview")

        self._tree.heading("timestamp",  text="Time")
        self._tree.heading("severity",   text="Severity")
        self._tree.heading("alert_type", text="Alert Type")
        self._tree.heading("filepath",   text="File")

        self._tree.column("timestamp",  width=160, stretch=False)
        self._tree.column("severity",   width=90,  stretch=False)
        self._tree.column("alert_type", width=280, stretch=False)
        self._tree.column("filepath",   width=400, stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Detail panel
        detail_frame = tk.Frame(self, bg=BG_CARD, padx=16, pady=10)
        detail_frame.pack(fill="x", padx=20, pady=(0, 12))

        tk.Label(detail_frame, text="Details", font=FONT_H2,
                 fg=TEXT_SECONDARY, bg=BG_CARD).pack(anchor="w")

        self._detail_text = tk.Text(
            detail_frame, bg="#0a1520", fg=TEXT_PRIMARY,
            font=FONT_MONO, relief="flat", height=5,
            state="disabled", wrap="word"
        )
        self._detail_text.pack(fill="x", pady=(4, 0))

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._alerts_cache = []
        self.refresh()

    def refresh(self):
        self._alerts_cache = get_recent_alerts(200)
        self._render()

    def _render(self):
        filter_val = self._filter_var.get()
        self._tree.delete(*self._tree.get_children())

        shown = 0
        for alert in self._alerts_cache:
            if filter_val != "ALL" and alert["severity"] != filter_val:
                continue
            sev   = alert["severity"]
            color = SEVERITY_COLORS.get(sev, TEXT_PRIMARY)
            iid   = self._tree.insert(
                "", "end",
                values=(alert["timestamp"], sev,
                        alert["alert_type"], alert["filepath"]),
                tags=(sev,)
            )
            self._tree.tag_configure(sev, foreground=color)
            shown += 1

        self._count_var.set(f"{shown} alert(s)")

    def _on_select(self, _event):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        values = self._tree.item(iid, "values")
        if not values:
            return

        # Find full details from cache
        ts, sev, atype, fp = values
        details = ""
        for alert in self._alerts_cache:
            if (alert["timestamp"] == ts and alert["severity"] == sev
                    and alert["alert_type"] == atype):
                details = alert.get("details", "")
                break

        self._detail_text.config(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.insert("end", details or "(no details)")
        self._detail_text.config(state="disabled")

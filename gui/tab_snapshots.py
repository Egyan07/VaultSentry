# =============================================================================
#   gui/tab_snapshots.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Snapshots tab — create, browse, diff, and delete baseline snapshots.
#   Allows forensic comparison: "what changed between last Tuesday and today?"
# =============================================================================

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from gui.theme import *
from core.database import (
    create_snapshot, list_snapshots, get_snapshot_files,
    diff_snapshots, delete_snapshot,
)
from utils.file_utils import format_size


class SnapshotsTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._snapshots: list[dict] = []
        self._build()

    # =========================================================================
    #   Build UI
    # =========================================================================

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, padx=20, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Baseline Snapshots", font=FONT_H1,
                 fg=ACCENT, bg=BG_PANEL).pack(side="left")

        # Action buttons
        btn_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=10)
        btn_frame.pack(fill="x")

        btn_cfg = dict(font=FONT_BODY, relief="flat", padx=14,
                       pady=6, cursor="hand2")

        tk.Button(btn_frame, text="📸  Save Snapshot",
                  bg=ACCENT_DIM, fg=TEXT_PRIMARY,
                  activebackground=ACCENT, activeforeground="white",
                  command=self._save_snapshot, **btn_cfg).pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="🔍  Diff Two Snapshots",
                  bg=BG_CARD, fg=TEXT_SECONDARY,
                  activebackground=BG_HOVER, activeforeground=TEXT_PRIMARY,
                  command=self._diff_selected, **btn_cfg).pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="🗑  Delete Selected",
                  bg="#3a1a1a", fg=CRITICAL_COLOR,
                  activebackground="#4a2020", activeforeground=CRITICAL_COLOR,
                  command=self._delete_selected, **btn_cfg).pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="↻  Refresh",
                  bg=BG_CARD, fg=TEXT_SECONDARY,
                  activebackground=BG_HOVER, activeforeground=TEXT_PRIMARY,
                  command=self.refresh, **btn_cfg).pack(side="right")

        self._status_var = tk.StringVar(value="")
        tk.Label(btn_frame, textvariable=self._status_var, font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(side="left", padx=12)

        # Snapshot list
        list_frame = tk.Frame(self, bg=BG_DARK, padx=20)
        list_frame.pack(fill="both", expand=True)

        tk.Label(list_frame, text="Saved Snapshots", font=FONT_H2,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(anchor="w", pady=(4, 4))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("SN.Treeview",
                         background=BG_CARD, foreground=TEXT_PRIMARY,
                         fieldbackground=BG_CARD, rowheight=22,
                         font=FONT_MONO)
        style.configure("SN.Treeview.Heading",
                         background=BG_PANEL, foreground=TEXT_PRIMARY,
                         font=FONT_H2, relief="flat")
        style.map("SN.Treeview",
                  background=[("selected", ACCENT_DIM)],
                  foreground=[("selected", "white")])

        snap_cols = ("id", "label", "created_at", "file_count", "notes")
        self._snap_tree = ttk.Treeview(list_frame, columns=snap_cols,
                                        show="headings", style="SN.Treeview",
                                        height=8, selectmode="extended")
        self._snap_tree.heading("id",          text="ID")
        self._snap_tree.heading("label",       text="Label")
        self._snap_tree.heading("created_at",  text="Created")
        self._snap_tree.heading("file_count",  text="Files")
        self._snap_tree.heading("notes",       text="Notes")

        self._snap_tree.column("id",         width=40,  stretch=False)
        self._snap_tree.column("label",      width=200, stretch=False)
        self._snap_tree.column("created_at", width=160, stretch=False)
        self._snap_tree.column("file_count", width=70,  stretch=False)
        self._snap_tree.column("notes",      width=300, stretch=True)

        snap_vsb = ttk.Scrollbar(list_frame, orient="vertical",
                                  command=self._snap_tree.yview)
        self._snap_tree.configure(yscrollcommand=snap_vsb.set)
        self._snap_tree.pack(side="left", fill="both", expand=True)
        snap_vsb.pack(side="right", fill="y")
        self._snap_tree.bind("<<TreeviewSelect>>", self._on_snap_select)

        # File detail panel
        detail_outer = tk.Frame(self, bg=BG_DARK, padx=20, pady=6)
        detail_outer.pack(fill="both", expand=True)

        self._detail_label = tk.Label(detail_outer,
                                       text="Select a snapshot to browse its files",
                                       font=FONT_H2, fg=TEXT_SECONDARY, bg=BG_DARK)
        self._detail_label.pack(anchor="w", pady=(0, 4))

        file_cols = ("filepath", "status", "sha256", "size")
        self._file_tree = ttk.Treeview(detail_outer, columns=file_cols,
                                        show="headings", style="SN.Treeview",
                                        height=8)
        self._file_tree.heading("filepath", text="File Path")
        self._file_tree.heading("status",   text="Status")
        self._file_tree.heading("sha256",   text="SHA-256 (first 16)")
        self._file_tree.heading("size",     text="Size")

        self._file_tree.column("filepath", width=500, stretch=True)
        self._file_tree.column("status",   width=90,  stretch=False)
        self._file_tree.column("sha256",   width=140, stretch=False)
        self._file_tree.column("size",     width=90,  stretch=False)

        self._file_tree.tag_configure("CHANGED",  foreground=WARNING_COLOR)
        self._file_tree.tag_configure("MISSING",  foreground=CRITICAL_COLOR)
        self._file_tree.tag_configure("CORRUPT",  foreground=CRITICAL_COLOR)
        self._file_tree.tag_configure("OK",       foreground=OK_COLOR)

        file_vsb = ttk.Scrollbar(detail_outer, orient="vertical",
                                  command=self._file_tree.yview)
        self._file_tree.configure(yscrollcommand=file_vsb.set)
        self._file_tree.pack(side="left", fill="both", expand=True)
        file_vsb.pack(side="right", fill="y")

        self.refresh()

    # =========================================================================
    #   Actions
    # =========================================================================

    def refresh(self):
        self._snapshots = list_snapshots()
        self._snap_tree.delete(*self._snap_tree.get_children())
        for snap in self._snapshots:
            self._snap_tree.insert("", "end", iid=str(snap["id"]),
                                    values=(snap["id"], snap["label"],
                                            snap["created_at"],
                                            snap["file_count"],
                                            snap["notes"] or ""))
        count = len(self._snapshots)
        self._status_var.set(f"{count} snapshot(s)")

    def _save_snapshot(self):
        label = simpledialog.askstring(
            "Save Snapshot",
            "Enter a label for this snapshot\n(e.g. 'Before client audit', '2026-03-15 clean'):",
            parent=self
        )
        if not label:
            return

        notes = simpledialog.askstring(
            "Notes (optional)",
            "Add any notes for this snapshot:",
            parent=self
        ) or ""

        self._status_var.set("Saving snapshot...")

        def run():
            snap_id = create_snapshot(label.strip(), notes.strip())
            if snap_id > 0:
                self.after(0, lambda: self._status_var.set(
                    f"Snapshot #{snap_id} saved — '{label}'"
                ))
                self.after(0, self.refresh)
            else:
                self.after(0, lambda: self._status_var.set(
                    "Failed — no baseline data found. Run baseline first."
                ))

        threading.Thread(target=run, daemon=True).start()

    def _on_snap_select(self, _event):
        selected = self._snap_tree.selection()
        if not selected:
            return
        snap_id = int(selected[0])
        snap = next((s for s in self._snapshots if s["id"] == snap_id), None)
        if not snap:
            return

        self._detail_label.config(
            text=f"Files in snapshot #{snap_id} — {snap['label']}  "
                 f"({snap['file_count']} files)"
        )
        self._file_tree.delete(*self._file_tree.get_children())
        files = get_snapshot_files(snap_id)
        for f in files:
            sha_short = (f["sha256"] or "")[:16]
            size_str  = format_size(f["file_size"] or 0)
            tag       = f["status"] if f["status"] in ("CHANGED", "MISSING", "CORRUPT") else "OK"
            self._file_tree.insert("", "end",
                                    values=(f["filepath"], f["status"],
                                            sha_short, size_str),
                                    tags=(tag,))

    def _diff_selected(self):
        selected = self._snap_tree.selection()
        if len(selected) != 2:
            messagebox.showinfo("Diff Snapshots",
                                "Select exactly 2 snapshots to diff.\n"
                                "Hold Ctrl and click to select two.")
            return

        id_a, id_b = int(selected[0]), int(selected[1])
        # Always diff older → newer (lower id = older)
        if id_a > id_b:
            id_a, id_b = id_b, id_a

        snap_a = next(s for s in self._snapshots if s["id"] == id_a)
        snap_b = next(s for s in self._snapshots if s["id"] == id_b)

        diff = diff_snapshots(id_a, id_b)
        self._show_diff_window(snap_a, snap_b, diff)

    def _show_diff_window(self, snap_a, snap_b, diff):
        win = tk.Toplevel(self)
        win.title(f"Diff: #{snap_a['id']} '{snap_a['label']}' → #{snap_b['id']} '{snap_b['label']}'")
        win.geometry("900x600")
        win.configure(bg=BG_DARK)

        # Summary bar
        summary = tk.Frame(win, bg=BG_CARD, padx=16, pady=10)
        summary.pack(fill="x")
        tk.Label(summary,
                 text=f"Added: {len(diff['added'])}   "
                      f"Removed: {len(diff['removed'])}   "
                      f"Changed: {len(diff['changed'])}   "
                      f"Unchanged: {len(diff['unchanged'])}",
                 font=FONT_H2, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")

        # Tabs for each category
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=8)

        categories = [
            ("changed",   f"Changed ({len(diff['changed'])})",   WARNING_COLOR),
            ("added",     f"Added ({len(diff['added'])})",        OK_COLOR),
            ("removed",   f"Removed ({len(diff['removed'])})",    CRITICAL_COLOR),
            ("unchanged", f"Unchanged ({len(diff['unchanged'])})", TEXT_MUTED),
        ]

        for key, tab_label, color in categories:
            frame = tk.Frame(nb, bg=BG_DARK)
            nb.add(frame, text=tab_label)

            if key == "changed":
                cols = ("filepath", "sha256_a", "sha256_b", "size_a", "size_b")
                tree = ttk.Treeview(frame, columns=cols, show="headings", style="SN.Treeview")
                tree.heading("filepath", text="File")
                tree.heading("sha256_a", text=f"Hash (#{snap_a['id']})")
                tree.heading("sha256_b", text=f"Hash (#{snap_b['id']})")
                tree.heading("size_a",   text=f"Size A")
                tree.heading("size_b",   text=f"Size B")
                tree.column("filepath", width=380, stretch=True)
                tree.column("sha256_a", width=130, stretch=False)
                tree.column("sha256_b", width=130, stretch=False)
                tree.column("size_a",   width=80,  stretch=False)
                tree.column("size_b",   width=80,  stretch=False)
                for item in diff[key]:
                    tree.insert("", "end", values=(
                        item["filepath"],
                        (item["sha256_a"] or "")[:16],
                        (item["sha256_b"] or "")[:16],
                        format_size(item["size_a"] or 0),
                        format_size(item["size_b"] or 0),
                    ))
            else:
                cols = ("filepath", "status", "size")
                tree = ttk.Treeview(frame, columns=cols, show="headings", style="SN.Treeview")
                tree.heading("filepath", text="File")
                tree.heading("status",   text="Status")
                tree.heading("size",     text="Size")
                tree.column("filepath", width=600, stretch=True)
                tree.column("status",   width=90,  stretch=False)
                tree.column("size",     width=90,  stretch=False)
                for item in diff[key]:
                    tree.insert("", "end", values=(
                        item["filepath"],
                        item.get("status", ""),
                        format_size(item.get("file_size", 0) or 0),
                    ))

            vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")

        tk.Button(win, text="Close", font=FONT_BODY,
                  bg=ACCENT_DIM, fg=TEXT_PRIMARY,
                  relief="flat", padx=14, pady=6,
                  command=win.destroy).pack(pady=8)

    def _delete_selected(self):
        selected = self._snap_tree.selection()
        if not selected:
            messagebox.showinfo("Delete Snapshot", "Select a snapshot to delete.")
            return

        ids = [int(iid) for iid in selected]
        if not messagebox.askyesno(
            "Delete Snapshot",
            f"Delete {len(ids)} snapshot(s)?\nThis cannot be undone."
        ):
            return

        for snap_id in ids:
            delete_snapshot(snap_id)

        self.refresh()
        self._status_var.set(f"Deleted {len(ids)} snapshot(s)")

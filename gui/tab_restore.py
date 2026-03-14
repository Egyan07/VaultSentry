# =============================================================================
#   gui/tab_restore.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Restore tab — lets the user:
#     1. Filter files by status (All / Changed / Missing / Corrupt)
#     2. Select a destination folder via dialog
#     3. Preview the restore plan (dry-run)
#     4. Execute with per-file overwrite prompts for conflicts
# =============================================================================

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from gui.theme import *
from core.restore import (
    get_restorable_files, plan_restore, execute_restore,
    RestorePlan, RestoreResult,
)
from utils.file_utils import format_size


class RestoreTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._plan:           RestorePlan | None = None
        self._destination:    str = ""
        self._running:        bool = False
        self._build()

    # =========================================================================
    #   Build UI
    # =========================================================================

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, padx=20, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Restore Files", font=FONT_H1,
                 fg=ACCENT, bg=BG_PANEL).pack(side="left")

        # ── Step 1: Filter + Destination ─────────────────────────────────────
        step1 = tk.Frame(self, bg=BG_CARD, padx=20, pady=14)
        step1.pack(fill="x", padx=20, pady=(14, 0))

        tk.Label(step1, text="Step 1 — Choose what to restore and where",
                 font=FONT_H2, fg=ACCENT, bg=BG_CARD).grid(
                     row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        tk.Label(step1, text="Restore:", font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_CARD).grid(row=1, column=0, sticky="w")

        self._filter_var = tk.StringVar(value="ALL")
        filters = [("All files", "ALL"), ("Changed only", "CHANGED"),
                   ("Missing only", "MISSING"), ("Corrupt only", "CORRUPT"),
                   ("Changed + Missing", "CHANGED_MISSING")]
        filter_menu = ttk.Combobox(
            step1, textvariable=self._filter_var,
            values=[f[0] for f in filters],
            state="readonly", width=22, font=FONT_BODY
        )
        filter_menu.grid(row=1, column=1, padx=(8, 24), sticky="w")
        self._filter_labels = {f[0]: f[1] for f in filters}

        tk.Label(step1, text="Destination:", font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_CARD).grid(row=1, column=2, sticky="w")

        self._dest_var = tk.StringVar(value="(no folder selected)")
        dest_label = tk.Label(step1, textvariable=self._dest_var,
                               font=FONT_MONO, fg=TEXT_PRIMARY, bg=BG_CARD,
                               width=40, anchor="w")
        dest_label.grid(row=1, column=3, padx=(8, 12), sticky="w")

        tk.Button(
            step1, text="📁  Browse...", font=FONT_BODY,
            bg=ACCENT_DIM, fg=TEXT_PRIMARY,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._browse_destination
        ).grid(row=1, column=4, padx=(0, 0))

        # ── Step 2: Preview ───────────────────────────────────────────────────
        step2 = tk.Frame(self, bg=BG_DARK, padx=20, pady=8)
        step2.pack(fill="x")

        tk.Label(step2, text="Step 2 — Preview restore plan",
                 font=FONT_H2, fg=TEXT_SECONDARY, bg=BG_DARK).pack(
                     side="left", pady=(10, 4))

        preview_btn = tk.Button(
            step2, text="🔍  Preview",
            font=FONT_BODY, bg=BG_CARD, fg=TEXT_SECONDARY,
            activebackground=BG_HOVER, activeforeground=TEXT_PRIMARY,
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=self._preview
        )
        preview_btn.pack(side="left", padx=12, pady=(10, 4))

        self._summary_var = tk.StringVar(value="")
        tk.Label(step2, textvariable=self._summary_var, font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(side="left", pady=(10, 4))

        # Treeview for plan preview
        tree_frame = tk.Frame(self, bg=BG_DARK, padx=20)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("RS.Treeview",
                         background=BG_CARD, foreground=TEXT_PRIMARY,
                         fieldbackground=BG_CARD, rowheight=20,
                         font=FONT_MONO)
        style.configure("RS.Treeview.Heading",
                         background=BG_PANEL, foreground=TEXT_PRIMARY,
                         font=FONT_H2, relief="flat")
        style.map("RS.Treeview",
                  background=[("selected", ACCENT_DIM)],
                  foreground=[("selected", "white")])

        cols = ("status", "source", "destination", "size", "conflict")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                   show="headings", style="RS.Treeview")
        self._tree.heading("status",      text="Status")
        self._tree.heading("source",      text="Source File")
        self._tree.heading("destination", text="Destination")
        self._tree.heading("size",        text="Size")
        self._tree.heading("conflict",    text="Conflict")

        self._tree.column("status",      width=90,  stretch=False)
        self._tree.column("source",      width=340, stretch=True)
        self._tree.column("destination", width=340, stretch=True)
        self._tree.column("size",        width=80,  stretch=False)
        self._tree.column("conflict",    width=80,  stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Colour tags
        self._tree.tag_configure("CHANGED",  foreground=WARNING_COLOR)
        self._tree.tag_configure("MISSING",  foreground=CRITICAL_COLOR)
        self._tree.tag_configure("CORRUPT",  foreground=CRITICAL_COLOR)
        self._tree.tag_configure("OK",       foreground=OK_COLOR)
        self._tree.tag_configure("conflict", foreground=WARNING_COLOR)

        # ── Step 3: Execute ───────────────────────────────────────────────────
        step3 = tk.Frame(self, bg=BG_DARK, padx=20, pady=10)
        step3.pack(fill="x")

        tk.Label(step3, text="Step 3 — Execute",
                 font=FONT_H2, fg=TEXT_SECONDARY, bg=BG_DARK).pack(side="left")

        self._restore_btn = tk.Button(
            step3, text="▶  Restore Files",
            font=FONT_H2, bg="#1a4a2a", fg=OK_COLOR,
            activebackground="#1e5a34", activeforeground=OK_COLOR,
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=self._execute
        )
        self._restore_btn.pack(side="left", padx=12)

        self._status_var = tk.StringVar(value="")
        tk.Label(step3, textvariable=self._status_var, font=FONT_BODY,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(side="left")

    # =========================================================================
    #   Actions
    # =========================================================================

    def _browse_destination(self):
        folder = filedialog.askdirectory(
            title="Select restore destination folder",
            mustexist=False
        )
        if folder:
            self._destination = folder
            self._dest_var.set(folder)
            self._plan = None
            self._summary_var.set("")
            self._tree.delete(*self._tree.get_children())

    def _get_status_filter(self) -> list[str] | None:
        label = self._filter_var.get()
        code  = self._filter_labels.get(label, "ALL")
        if code == "ALL":
            return None
        if code == "CHANGED_MISSING":
            return ["CHANGED", "MISSING"]
        return [code]

    def _preview(self):
        if not self._destination:
            messagebox.showwarning("VaultSentry",
                                   "Please select a destination folder first.")
            return

        status_filter = self._get_status_filter()
        items = get_restorable_files(status_filter)

        if not items:
            messagebox.showinfo("VaultSentry",
                                "No files match the selected filter.")
            return

        self._plan = plan_restore(items, self._destination)
        self._render_plan()

    def _render_plan(self):
        if not self._plan:
            return

        self._tree.delete(*self._tree.get_children())
        plan = self._plan

        for item in plan.items:
            src_short  = "..." + item.filepath[-50:]  if len(item.filepath)  > 53 else item.filepath
            dest_short = "..." + item.dest_path[-50:] if len(item.dest_path) > 53 else item.dest_path
            conflict   = "⚠ exists" if item.exists_at_dest else ""
            size_str   = format_size(item.file_size)
            missing    = not os.path.exists(item.filepath)
            tag        = item.status if item.status in ("CHANGED", "MISSING", "CORRUPT") else "OK"
            if item.exists_at_dest:
                tag = "conflict"

            self._tree.insert("", "end",
                               values=(item.status, src_short,
                                       dest_short, size_str, conflict),
                               tags=(tag,))

        conflicts   = plan.already_exist
        missing_src = plan.missing_src
        total_size  = format_size(plan.total_size)

        summary = (
            f"{len(plan.items)} file(s) — {total_size}  |  "
            f"{conflicts} conflict(s)  |  "
            f"{missing_src} source(s) missing"
        )
        self._summary_var.set(summary)

    def _execute(self):
        if self._running:
            messagebox.showwarning("VaultSentry", "A restore is already running.")
            return

        if not self._plan:
            messagebox.showwarning("VaultSentry",
                                   "Run Preview first before executing restore.")
            return

        if not self._plan.items:
            messagebox.showinfo("VaultSentry", "No files to restore.")
            return

        if not messagebox.askyesno(
            "Confirm Restore",
            f"This will copy {len(self._plan.items)} file(s) to:\n\n"
            f"{self._destination}\n\n"
            f"Subfolder structure will be preserved.\n\n"
            f"Continue?"
        ):
            return

        # Handle conflicts — ask per file
        overwrite_set: set[str] = set()
        skip_set:      set[str] = set()

        conflicts = [i for i in self._plan.items if i.exists_at_dest]
        for item in conflicts:
            answer = messagebox.askyesnocancel(
                "File Exists",
                f"This file already exists at the destination:\n\n"
                f"{item.dest_path}\n\n"
                f"Overwrite?"
            )
            if answer is True:
                overwrite_set.add(item.dest_path)
            elif answer is False:
                skip_set.add(item.dest_path)
            else:
                # Cancel — abort entire restore
                self._status_var.set("Restore cancelled.")
                return

        # Create destination folder if needed
        try:
            os.makedirs(self._destination, exist_ok=True)
        except OSError as e:
            messagebox.showerror("VaultSentry",
                                 f"Cannot create destination folder:\n{e}")
            return

        self._running = True
        self._restore_btn.config(state="disabled")
        self._status_var.set("Restoring...")

        def run():
            def progress(current, total, filepath):
                self.after(0, lambda: self._status_var.set(
                    f"Restoring {current}/{total} — {os.path.basename(filepath)}"
                ))

            result = execute_restore(
                plan=self._plan,
                overwrite_all=False,
                skip_existing=False,
                overwrite_set=overwrite_set,
                progress_callback=progress,
            )

            def done():
                self._running = False
                self._restore_btn.config(state="normal")

                msg = (
                    f"Restore complete.\n\n"
                    f"  Restored : {result.restored}\n"
                    f"  Skipped  : {result.skipped}\n"
                    f"  Failed   : {result.failed}\n"
                    f"  Duration : {result.duration:.1f}s"
                )
                if result.errors:
                    msg += f"\n\nErrors:\n" + "\n".join(result.errors[:5])

                level = "info" if result.failed == 0 else "warning"
                color = OK_COLOR if result.failed == 0 else WARNING_COLOR
                self._status_var.set(
                    f"Done — {result.restored} restored, "
                    f"{result.skipped} skipped, {result.failed} failed"
                )

                if result.failed > 0:
                    messagebox.showwarning("Restore Complete", msg)
                else:
                    messagebox.showinfo("Restore Complete", msg)

            self.after(0, done)

        threading.Thread(target=run, daemon=True).start()

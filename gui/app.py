# =============================================================================
#   gui/app.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Main application window with tabbed interface.
# =============================================================================

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from gui.theme import *
from gui.tab_dashboard  import DashboardTab
from gui.tab_alerts     import AlertsTab
from gui.tab_reports    import ReportsTab
from gui.tab_restore    import RestoreTab
from gui.tab_snapshots  import SnapshotsTab
from gui.tab_settings   import SettingsTab

from core.database import init_database
from core.scanner  import create_baseline, verify_backups
from config        import APP_NAME, APP_VERSION


class VaultSentryApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION} — Red Parrot Accounting Ltd")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=BG_DARK)

        self._scanning = False
        self._build()
        self._start_auto_refresh()

    def _build(self):
        # Tab bar (manual — not ttk.Notebook, for full style control)
        tab_bar = tk.Frame(self, bg=BG_PANEL, height=42)
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)

        self._tab_buttons  = {}
        self._tab_frames   = {}
        self._active_tab   = tk.StringVar(value="dashboard")

        # Content area
        self._content = tk.Frame(self, bg=BG_DARK)
        self._content.pack(fill="both", expand=True)

        # Create tabs
        self._dash_tab      = DashboardTab(
            self._content,
            on_baseline=self._run_baseline,
            on_verify=self._run_verify
        )
        self._alerts_tab    = AlertsTab(self._content)
        self._reports_tab   = ReportsTab(self._content)
        self._restore_tab   = RestoreTab(self._content)
        self._snapshots_tab = SnapshotsTab(self._content)
        self._settings_tab  = SettingsTab(self._content)

        tabs = [
            ("dashboard",  "  Dashboard  ", self._dash_tab),
            ("alerts",     "  Alerts     ", self._alerts_tab),
            ("reports",    "  Reports    ", self._reports_tab),
            ("restore",    "  Restore    ", self._restore_tab),
            ("snapshots",  "  Snapshots  ", self._snapshots_tab),
            ("settings",   "  Settings   ", self._settings_tab),
        ]

        for key, label, frame in tabs:
            self._tab_frames[key] = frame

            btn = tk.Button(
                tab_bar, text=label, font=FONT_H2,
                bg=BG_PANEL, fg=TEXT_SECONDARY,
                activebackground=BG_HOVER, activeforeground=TEXT_PRIMARY,
                relief="flat", bd=0, padx=8, pady=8, cursor="hand2",
                command=lambda k=key: self._switch_tab(k)
            )
            btn.pack(side="left")
            self._tab_buttons[key] = btn

        self._switch_tab("dashboard")

    def _switch_tab(self, key: str):
        for k, frame in self._tab_frames.items():
            frame.pack_forget()

        for k, btn in self._tab_buttons.items():
            if k == key:
                btn.config(bg=BG_DARK, fg=ACCENT,
                            relief="flat",
                            font=("Consolas", 11, "bold"))
            else:
                btn.config(bg=BG_PANEL, fg=TEXT_SECONDARY,
                            font=FONT_H2)

        self._tab_frames[key].pack(fill="both", expand=True)
        self._active_tab.set(key)

        if key == "alerts":
            self._alerts_tab.refresh()

    def _run_baseline(self):
        if self._scanning:
            messagebox.showwarning(APP_NAME, "A scan is already running.")
            return

        if not messagebox.askyesno(
            "Create Baseline",
            "This will hash all files in the configured backup paths and store "
            "them as the known-good baseline.\n\n"
            "Re-running will update all existing records.\n\n"
            "Continue?"
        ):
            return

        self._scanning = True
        self._dash_tab.set_status("Building baseline...")
        self._dash_tab.start_progress()
        self._dash_tab.log_line("=" * 60, "muted")
        self._dash_tab.log_line("BASELINE MODE started", "info")

        def run():
            try:
                def progress(current, total, filepath):
                    self.after(0, lambda: self._dash_tab.set_status(
                        f"Hashing {current}/{total} — {filepath[-50:]}"
                    ))

                count = create_baseline(progress_callback=progress)
                self.after(0, lambda: self._dash_tab.log_line(
                    f"Baseline complete — {count} files hashed.", "ok"))
                self.after(0, lambda: self._dash_tab.set_status(
                    f"Baseline complete — {count} files"))
            except Exception as e:
                self.after(0, lambda: self._dash_tab.log_line(
                    f"ERROR: {e}", "critical"))
            finally:
                self.after(0, self._dash_tab.stop_progress)
                self.after(0, self._dash_tab.refresh_stats)
                self._scanning = False

        threading.Thread(target=run, daemon=True).start()

    def _run_verify(self):
        if self._scanning:
            messagebox.showwarning(APP_NAME, "A scan is already running.")
            return

        self._scanning = True
        self._dash_tab.set_status("Running verification...")
        self._dash_tab.start_progress()
        self._dash_tab.log_line("=" * 60, "muted")
        self._dash_tab.log_line("VERIFICATION started", "info")

        def run():
            try:
                def progress(step, message):
                    self.after(0, lambda: self._dash_tab.log_line(message, "info"))
                    self.after(0, lambda: self._dash_tab.set_status(message))

                results, alerts_raised = verify_backups(progress_callback=progress)

                summary = (
                    f"Verification complete — "
                    f"{len(results)} files checked, "
                    f"{alerts_raised} alert(s) raised"
                )
                level = "critical" if alerts_raised > 0 else "ok"
                self.after(0, lambda: self._dash_tab.log_line(summary, level))
                self.after(0, lambda: self._dash_tab.set_status(summary))

                # Log individual issues
                for r in results:
                    if r["status"] != "OK":
                        msg = f"  [{r['severity']}] {r['status']} — {r['filepath'][-60:]}"
                        lvl = "critical" if r["severity"] == "CRITICAL" else "warning"
                        self.after(0, lambda m=msg, l=lvl: self._dash_tab.log_line(m, l))

            except SystemExit:
                self.after(0, lambda: self._dash_tab.log_line(
                    "No baseline found. Create a baseline first.", "critical"))
                self.after(0, lambda: self._dash_tab.set_status("No baseline"))
            except Exception as e:
                self.after(0, lambda: self._dash_tab.log_line(
                    f"ERROR: {e}", "critical"))
            finally:
                self.after(0, self._dash_tab.stop_progress)
                self.after(0, self._dash_tab.refresh_stats)
                self._scanning = False

        threading.Thread(target=run, daemon=True).start()

    def _start_auto_refresh(self):
        """Refresh dashboard stats every 30 seconds."""
        self._dash_tab.refresh_stats()
        self.after(30_000, self._start_auto_refresh)


def launch():
    init_database()
    app = VaultSentryApp()
    app.mainloop()

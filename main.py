# =============================================================================
#
#  __   __          _ _   ____  ___ _ __ | |_ _ __ _   _
#  \ \ / /_ _ _   _| | |_/ ___|/ _ \ '_ \| __| '__| | | |
#   \ V / _` | | | | | |\__ \  __/ | | | |_| |  | |_| |
#    \_/ \__,_|_,___|_|_||___/\___|_| |_|\__|_|   \__, |
#                                                   |___/
#
# =============================================================================
#   Tool    : VaultSentry v1.0
#   Author  : Egyan
#   Company : Red Parrot Accounting Ltd
#   Purpose : Backup integrity monitoring — SHA-256 + entropy analysis
#             Detects tampering, ransomware, corruption, missing files,
#             and stale backups.
#   Runs    : Nightly via Windows Task Scheduler or on-demand via GUI
#   Logs    : C:\SecurityLogs\VaultSentry\
# =============================================================================

import sys
import argparse
import traceback
from datetime import datetime

from logger import log
from config import LOG_FILE, REPORT_DIR, APP_NAME, APP_VERSION
from core.database import init_database
from core.scanner  import create_baseline, verify_backups
from core.reports  import generate_excel_report
from core.alerts   import raise_alert


def print_banner():
    print()
    print("=" * 70)
    print(f"  {APP_NAME} v{APP_VERSION}")
    print("  Egyan | Red Parrot Accounting Ltd")
    print("  Backup integrity monitoring — SHA-256 + entropy analysis")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()


def show_status():
    """Quick console status summary from the database."""
    import os, sqlite3
    from config import DB_PATH

    print()
    print("=" * 60)
    print(f"  {APP_NAME} v{APP_VERSION} — STATUS")
    print("  Red Parrot Accounting Ltd")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print("  No database found. Run --baseline first.")
        print("=" * 60)
        return

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM file_hashes")
    total = cur.fetchone()[0]

    def count(status):
        cur.execute("SELECT COUNT(*) FROM file_hashes WHERE status=?", (status,))
        return cur.fetchone()[0]

    ok      = count("OK")
    changed = count("CHANGED")
    missing = count("MISSING")
    corrupt = count("CORRUPT")

    cur.execute(
        "SELECT run_time, files_scanned, alerts_raised "
        "FROM scan_runs ORDER BY id DESC LIMIT 1"
    )
    last = cur.fetchone()
    conn.close()

    print(f"  Database   : {DB_PATH}")
    print(f"  Total files: {total}")
    print(f"  OK         : {ok}")
    print(f"  Changed    : {changed}  {'<-- WARNING'  if changed > 0 else ''}")
    print(f"  Missing    : {missing}  {'<-- CRITICAL' if missing > 0 else ''}")
    print(f"  Corrupt    : {corrupt}  {'<-- CRITICAL' if corrupt > 0 else ''}")
    if last:
        print(f"  Last scan  : {last[0]}  ({last[1]} files, {last[2]} alerts)")
    print("=" * 60)
    print()


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="main",
        description=(
            f"{APP_NAME} v{APP_VERSION} — Backup integrity monitor\n"
            "Egyan | Red Parrot Accounting Ltd"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--gui", action="store_true",
        help="Launch the graphical dashboard"
    )
    group.add_argument(
        "--baseline", action="store_true",
        help="First-time setup: hash all backup files and store as baseline"
    )
    group.add_argument(
        "--verify", action="store_true",
        help="Nightly check: compare current files against baseline"
    )
    group.add_argument(
        "--digest", action="store_true",
        help="Send the daily digest email immediately (on-demand)"
    )
    group.add_argument(
        "--snapshot", metavar="LABEL",
        help="Save a named snapshot of the current baseline state"
    )
    group.add_argument(
        "--list-snapshots", action="store_true",
        help="List all saved snapshots"
    )
    group.add_argument(
        "--restore", action="store_true",
        help="Restore files from backup — interactive CLI restore"
    )
    group.add_argument(
        "--report", action="store_true",
        help="Generate an Excel report from the current database state"
    )
    group.add_argument(
        "--status", action="store_true",
        help="Print a quick status summary to the console"
    )
    return parser


def _cli_restore():
    """Interactive CLI restore — headless mode for scripting."""
    from core.restore import get_restorable_files, plan_restore, execute_restore

    print("\nAvailable status filters:")
    print("  1. All files")
    print("  2. Changed only")
    print("  3. Missing only")
    print("  4. Corrupt only")
    print("  5. Changed + Missing")

    choice = input("\nFilter [1-5, default=1]: ").strip() or "1"
    filter_map = {
        "1": None,
        "2": ["CHANGED"],
        "3": ["MISSING"],
        "4": ["CORRUPT"],
        "5": ["CHANGED", "MISSING"],
    }
    status_filter = filter_map.get(choice, None)

    items = get_restorable_files(status_filter)
    if not items:
        print("\nNo files match the selected filter.")
        return

    destination = input("\nRestore destination folder: ").strip()
    if not destination:
        print("No destination specified. Aborting.")
        return

    plan = plan_restore(items, destination)

    print(f"\nRestore plan:")
    print(f"  Files     : {len(plan.items)}")
    print(f"  Conflicts : {plan.already_exist} (files already exist at destination)")
    print(f"  Missing   : {plan.missing_src} (source files not found)")

    confirm = input("\nProceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Restore cancelled.")
        return

    import os
    os.makedirs(destination, exist_ok=True)

    overwrite_set: set[str] = set()
    for item in plan.items:
        if item.exists_at_dest:
            ans = input(
                f"  File exists: {item.dest_path}\n  Overwrite? [y/N]: "
            ).strip().lower()
            if ans == "y":
                overwrite_set.add(item.dest_path)

    result = execute_restore(
        plan=plan,
        overwrite_set=overwrite_set,
        progress_callback=lambda c, t, f: print(
            f"  [{c}/{t}] {os.path.basename(f)}"
        )
    )

    print(f"\nRestore complete:")
    print(f"  Restored : {result.restored}")
    print(f"  Skipped  : {result.skipped}")
    print(f"  Failed   : {result.failed}")
    if result.errors:
        print("\nErrors:")
        for e in result.errors:
            print(f"  {e}")


def main():
    print_banner()

    parser = build_arg_parser()
    args   = parser.parse_args()

    init_database()

    try:
        if args.gui:
            from gui.app import launch
            launch()

        elif args.baseline:
            log.info("Mode: BASELINE")
            create_baseline()

        elif args.verify:
            log.info("Mode: VERIFY")
            results, alerts_raised = verify_backups()
            if datetime.now().weekday() == 0 or alerts_raised > 0:
                generate_excel_report(results)
                log.info("Report saved to: %s", REPORT_DIR)

        elif args.digest:
            log.info("Mode: DIGEST")
            from core.digest import send_digest
            from config import EMAIL_ENABLED
            if not EMAIL_ENABLED:
                print("\n[WARNING] EMAIL_ENABLED is False in config.py.")
                print("Set EMAIL_ENABLED = True and configure SMTP to send the digest.\n")
            ok = send_digest()
            print(f"\nDigest {'sent successfully.' if ok else 'failed — check log for details.'}\n")

        elif args.snapshot:
            log.info("Mode: SNAPSHOT")
            from core.database import create_snapshot
            snap_id = create_snapshot(args.snapshot)
            if snap_id > 0:
                print(f"\nSnapshot #{snap_id} saved: '{args.snapshot}'")
            else:
                print("\nFailed — run --baseline first.")

        elif args.list_snapshots:
            from core.database import list_snapshots
            snaps = list_snapshots()
            if not snaps:
                print("\nNo snapshots found. Create one with --snapshot 'label'")
            else:
                print(f"\n{'ID':<6} {'Created':<22} {'Files':<8} Label")
                print("-" * 70)
                for s in snaps:
                    print(f"{s['id']:<6} {s['created_at']:<22} {s['file_count']:<8} {s['label']}")
            print()

        elif args.restore:
            log.info("Mode: RESTORE")
            _cli_restore()

        elif args.report:
            log.info("Mode: REPORT")
            path = generate_excel_report()
            if path:
                print(f"\nReport saved to: {path}")

        elif args.status:
            show_status()

    except KeyboardInterrupt:
        log.info("%s stopped by user.", APP_NAME)

    except Exception as e:
        log.critical("Unexpected error: %s", e)
        log.critical(traceback.format_exc())
        raise_alert(
            "CRITICAL", f"{APP_NAME.upper()} CRASHED", "N/A",
            f"Script crashed: {e}\nCheck log: {LOG_FILE}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

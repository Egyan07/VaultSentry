# VaultSentry v1.0

**Backup Integrity Monitor for Windows**
Detects tampering, ransomware encryption, corruption, missing files, stale backups, and sudden backup size drops — nightly, automatically.

> Built by Egyan | Red Parrot Accounting Ltd

---

## What It Does

VaultSentry hashes every file in your backup folders on first run and stores them as a known-good baseline. Every night it re-hashes them and compares. If anything has changed, gone missing, been corrupted, looks encrypted, or total backup size has dropped — it fires an alert. A daily digest email summarises everything in one clean report each morning.

**Detects:**
- Hash changes — tampering or corruption since baseline
- Ransomware encryption — hash change + entropy spike above 7.8
- Ransom notes — new files named `readme_decrypt`, `how_to_restore` etc.
- Missing files — backup deleted or moved
- Stale backups — newest backup older than configured threshold
- Corrupt files — ZIP/Excel/Word structural validation failures
- Backup size drops — total size drops ≥30% vs previous run

---

## Features

| Feature | Detail |
|---|---|
| SHA-256 hashing | Cryptographically strong integrity verification |
| Shannon entropy analysis | Detects ransomware encryption without signatures |
| 4-step nightly pipeline | Baseline verify → new file scan → age check → structural integrity |
| Backup size trend tracking | Alerts on drops, sparkline chart on dashboard |
| Alert deduplication | Same alert suppressed within 24 hours |
| Daily email digest | One HTML summary per day — not a flood of individual alert emails |
| Baseline snapshots | Named point-in-time copies, diff any two to see what changed |
| Restore capability | Copy files back with subfolder structure preserved |
| Desktop GUI | Dark blue dashboard — Dashboard, Alerts, Reports, Restore, Snapshots, Settings |
| Excel reports | Colour-coded 3-sheet reports |
| Email alerts | SMTP with proper TLS certificate verification |
| Windows Task Scheduler | Nightly at 02:00 automatically |
| CLI mode | Headless operation for scripting |

---

## Requirements

- Windows 10 or 11
- Python 3.10+
- `pip install openpyxl` — for Excel reports

---

## Installation

```cmd
right-click Install_VaultSentry.bat → Run as administrator
```

Installs to `C:\SecurityLogs\VaultSentry\`, creates scheduled task, runs baseline.

---

## Usage

```cmd
python main.py --gui                              # Launch GUI
python main.py --baseline                         # First-time baseline hash
python main.py --verify                           # Nightly verification
python main.py --snapshot "Before audit Mar 2026" # Save named snapshot
python main.py --list-snapshots                   # List all snapshots
python main.py --restore                          # Interactive CLI restore
python main.py --digest                           # Send daily digest now
python main.py --report                           # Generate Excel report
python main.py --status                           # Quick console summary
```

---

## GUI Tabs

| Tab | What it does |
|---|---|
| **Dashboard** | Live stats cards, backup size trend sparkline (last 14 runs), scan controls, live log |
| **Alerts** | Full alert history, severity filter, detail panel |
| **Reports** | Generate and browse Excel reports |
| **Restore** | Filter by status → preview plan → execute with per-file overwrite prompts |
| **Snapshots** | Save snapshots, browse files, diff two snapshots, delete old ones |
| **Settings** | Config viewer, path checks, env var status, quick actions |

---

## Email Setup

**Individual alerts** — set `EMAIL_ENABLED = True` in `config.py`.

**Daily digest** — set `DIGEST_ENABLED = True` and `DIGEST_TIME = 8` (hour to send after).
The digest sends one HTML email per day with a full summary — scan results, all alerts from the last 25 hours, and status banner. Individual CRITICAL alerts still fire immediately regardless.

Store your password as an environment variable — never in config.py:

```powershell
# Run PowerShell as Administrator
[System.Environment]::SetEnvironmentVariable(
  'VAULTSENTRY_EMAIL_PASSWORD', 'your_app_password', 'Machine')
```

---

## Tests

162 unit tests across 8 modules. 73% coverage.

```bash
pip install pytest pytest-cov
pytest tests/ -v
```

| Module | Tests | What it covers |
|---|---|---|
| `test_file_utils.py`  | 35 | SHA-256, entropy, file walking, integrity |
| `test_database.py`    | 20 | DB layer — tables, constraints, stats |
| `test_alerts.py`      |  6 | Alert dispatch, dedup, TLS verified |
| `test_scanner.py`     | 16 | 4-step verification pipeline |
| `test_restore.py`     | 20 | Restore engine — plan, execute, edge cases |
| `test_snapshots.py`   | 23 | Snapshot CRUD + diff |
| `test_size_trend.py`  | 12 | Size tracking, drop alert |
| `test_digest.py`      | 30 | HTML/text builder, send logic, scheduling |

---

## Project Structure

```
VaultSentry/
├── main.py                   # Entry point — CLI + GUI launcher
├── config.py                 # All settings ← edit before deploying
├── logger.py                 # Rotating log handler
├── Install_VaultSentry.bat
├── Uninstall_VaultSentry.bat
├── .github/workflows/ci.yml  # Python 3.10/3.11/3.12 CI
├── core/
│   ├── database.py           # DB layer — all queries, stats, snapshots, size trend, digest data
│   ├── alerts.py             # Alert dispatcher — popup, msg.exe, email (TLS verified)
│   ├── scanner.py            # Baseline + 4-step verification + size drop check
│   ├── restore.py            # Restore engine — plan and execute
│   ├── digest.py             # Daily HTML digest builder and sender
│   └── reports.py            # Excel report generator
├── gui/
│   ├── app.py                # Main window + tab switching
│   ├── theme.py              # Dark blue colour scheme
│   ├── tab_dashboard.py      # Stats + size trend sparkline + live log
│   ├── tab_alerts.py         # Alert history with filter
│   ├── tab_reports.py        # Generate + browse reports
│   ├── tab_restore.py        # Restore with preview + per-file prompts
│   ├── tab_snapshots.py      # Snapshot list, diff viewer, delete
│   └── tab_settings.py       # Config viewer + quick actions
├── utils/
│   └── file_utils.py         # SHA-256, entropy, file walking, integrity check
└── tests/
    ├── conftest.py
    ├── test_file_utils.py
    ├── test_database.py
    ├── test_alerts.py
    ├── test_scanner.py
    ├── test_restore.py
    ├── test_snapshots.py
    ├── test_size_trend.py
    └── test_digest.py
```

---

## How Ransomware Detection Works

Shannon entropy measures byte-level randomness. Normal files score 4.0–6.5. Encrypted files score 7.5–8.0. When a hash changes AND entropy spikes above 7.8, VaultSentry fires CRITICAL: **RANSOMWARE SUSPECTED — BACKUP ENCRYPTED**.

The size trend check adds a second layer: if total backup size drops ≥30% overnight, that is a second CRITICAL alert — ransomware often replaces originals with smaller encrypted versions before the ransom note appears.

---

## Changelog

**v1.0** *(current)*

*Phase 5 — Daily email digest*
- `core/digest.py` — `build_digest_html()`, `build_digest_text()`, `send_digest()`, `should_send_digest()`
- HTML digest email — status banner, scan summary table, alert table, Red Parrot branding
- Plain-text fallback for email clients that don't render HTML
- `DIGEST_ENABLED` and `DIGEST_TIME` config options
- Auto-triggered after `--verify` when time condition met; no duplicate sends per day
- `--digest` CLI flag for on-demand send
- `get_digest_data()` in database layer — queries alerts + last scan run for the period
- 30 tests in `test_digest.py`, coverage raised to 73%

*Phase 4 — Backup size trend tracking*
- `total_backup_size` stored on every verify run
- CRITICAL alert when size drops ≥30% vs previous run
- Size trend sparkline on Dashboard (last 14 runs, drops highlighted red)
- `get_size_trend()`, `get_previous_backup_size()`, `_calculate_total_backup_size()`
- 12 tests in `test_size_trend.py`

*Phase 3 — Baseline snapshot versioning*
- `snapshots` and `snapshot_files` DB tables
- `create_snapshot()`, `list_snapshots()`, `get_snapshot_files()`, `diff_snapshots()`, `delete_snapshot()`
- Snapshots GUI tab with tabbed diff viewer (Added / Removed / Changed / Unchanged)
- `--snapshot "label"` and `--list-snapshots` CLI flags
- 23 tests in `test_snapshots.py`

*Phase 2 — Restore capability*
- `core/restore.py` — plan and execute file restores with subfolder structure
- Restore GUI tab — filter, dry-run preview, per-file overwrite prompts via dialog
- `--restore` CLI flag with interactive prompts
- 20 tests in `test_restore.py`

*Phase 1 — Tests + CI*
- Fixed `starttls()` → `ssl.create_default_context()` (MITM vulnerability)
- Alert deduplication (24h cooldown)
- 76 tests, CI on Python 3.10/3.11/3.12

---

## Disclaimer

VaultSentry detects integrity violations — it does not restore files or block ransomware. Treat any CRITICAL alert as an immediate incident.

---

*Built by Egyan | Red Parrot Accounting Ltd*

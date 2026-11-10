<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/storage-SQLite-07405E?logo=sqlite&logoColor=white" alt="SQLite">
  <a href="https://github.com/Egyan07/VaultSentry/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Egyan07/VaultSentry/ci.yml?label=CI&logo=githubactions&logoColor=white" alt="CI"></a>
</p>

# VaultSentry

A nightly integrity check for a backup drive. It hashes every file, compares the drive against a trusted baseline, and tells you when something changed that should not have.

## Why this exists

A backup you have never verified is a folder of files you hope are intact. Ransomware is the reason to check. The first thing modern ransomware does after encrypting a share is look for the backups and encrypt those too, and the backup job keeps reporting success because it is still copying files, just not the files you wanted.

VaultSentry answers one question every night: is the backup still what it was yesterday, and if not, why.

## What it checks

Verification runs four passes and ends with a size trend check.

| Pass | What it does |
|---|---|
| Baseline files | Re-hashes every file in the baseline and compares against the stored SHA-256 |
| New files | Picks up files that appeared since the last run and records them |
| Missing files | Reports files that vanished or moved, by path |
| Integrity | Confirms each changed file still opens and can be read |
| Size trend | Compares total backup size against the previous run and alerts on a drop of 30% or more |

## Ransomware detection

Two independent signals, because either one alone produces noise.

**Entropy.** Encrypted content sits near the top of the scale. VaultSentry computes Shannon entropy per file. A file whose hash changed and whose entropy exceeds 7.8 raises `CRITICAL: RANSOMWARE SUSPECTED`.

**Size drop.** If the whole backup shrinks by 30% or more overnight, something deleted or overwrote a large amount of data. That raises its own critical alert regardless of entropy.

Archives and Office formats are excluded from the entropy escalation. `.zip`, `.pdf`, `.xlsx`, `.docx`, `.gz`, `.7z`, `.rar`, `.xls` and `.tar` naturally sit above 7.8 when healthy, so treating them as encrypted would fire every night. A hash change in one of those still raises a warning, and the integrity pass still runs.

## Alerts

- **Desktop popup** and `msg.exe` message to the admin workstation
- **Email on critical events**, with the password read from `VAULTSENTRY_EMAIL_PASSWORD`
- **Daily digest** at the configured hour, one HTML mail with the last 25 hours of alerts, the verification result and backup health
- **Cooldown** of 24 hours per file and alert type, so one broken file is one alert and not one per run

## Install

Run the installer as administrator:

```cmd
Install_VaultSentry.bat
```

It installs to `C:\SecurityLogs\VaultSentry\`, registers a Windows scheduled task for the nightly run and creates the first baseline.

Then set your backup paths in `config.py`:

```python
BACKUP_PATHS = [
    r"D:\Backups",
]
```

Nothing is monitored until `BACKUP_PATHS` points at real folders.

## Usage

```cmd
python main.py --baseline              create or refresh the trusted baseline
python main.py --verify                run the nightly verification
python main.py --gui                   desktop dashboard
python main.py --snapshot "before audit"   save a named point-in-time baseline
python main.py --list-snapshots        list saved snapshots
python main.py --restore               interactive restore from backup
python main.py --digest                send the daily digest now
python main.py --report                write an Excel report
python main.py --status                quick console summary
```

The flags are mutually exclusive, which is deliberate. One run does one job, and the scheduled task calls `--verify`.

## Dashboard

| Tab | What it shows |
|---|---|
| Dashboard | File counts, backup size trend, scan controls |
| Alerts | Alert history with severity filter |
| Reports | Generate and open Excel reports |
| Restore | Restore plan preview before anything is written |
| Snapshots | Create, browse, diff and delete snapshots |
| Settings | Current configuration and diagnostics |

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `BACKUP_PATHS` | empty | Folders to monitor. Nothing works until this is set |
| `MONITORED_EXTENSIONS` | document and archive types | File types included in hashing |
| `MAX_BACKUP_AGE_HOURS` | `25` | Newest file older than this raises a stale backup warning |
| `ENTROPY_SPIKE_THRESHOLD` | `7.8` | Entropy above this on a changed file means suspected encryption |
| `SIZE_DROP_ALERT_PERCENT` | `30` | Total size drop that triggers a critical alert |
| `ALERT_COOLDOWN_HOURS` | `24` | Suppression window per file and alert type |
| `EMAIL_ENABLED` | `False` | Turns alert email on |
| `DIGEST_ENABLED` | `False` | Turns the daily HTML digest on |
| `DIGEST_TIME` | `8` | Hour of day the digest goes out |

Credentials stay out of the repository. Set the SMTP password once:

```powershell
[System.Environment]::SetEnvironmentVariable(
  'VAULTSENTRY_EMAIL_PASSWORD', 'your_app_password', 'Machine')
```

## Tests

162 unit tests covering the scanner, database layer, alerts, digest, restore, snapshots, size trend and file utilities.

```bash
pip install pytest pytest-cov
pytest tests/ -v
```

CI runs them on Python 3.10, 3.11 and 3.12.

## Structure

```
vaultsentry/
├── main.py               CLI entry point
├── config.py             paths, thresholds, email settings
├── logger.py
├── core/
│   ├── scanner.py        baseline creation and the four verification passes
│   ├── database.py       SQLite schema, file records, snapshots, size trend
│   ├── alerts.py         severity, deduplication, popup, msg.exe, email
│   ├── digest.py         daily HTML summary
│   ├── reports.py        multi-sheet Excel output
│   └── restore.py        restore planning and execution
├── gui/                  Tkinter tabs and theme
├── utils/file_utils.py   hashing, entropy, file listing
└── tests/
```

## Limits

| Limit | Detail |
|---|---|
| Local disks only | No S3, Backblaze or network shares. A remote copy is a separate job |
| Detects, does not block | Ransomware already running is not stopped. Nothing is restored automatically |
| Hash cost | Every file is read every night. A large backup takes as long as reading it takes |
| Baseline trust | If the baseline is created after encryption has started, the encrypted state becomes the reference |
| Windows only | Scheduled task and `msg.exe` are Windows specific |
| Entropy is a heuristic | Compression, media files and encrypted documents sit high on the scale. The exclusion list exists for that reason |

## Changelog

**1.0.1**

- Digest date persisted in a settings table, so the once-per-day guard survives a task restart
- Test credential file removed from the repository, secret patterns added to `.gitignore`
- Email failures surfaced in the dashboard instead of only in the log
- Entropy false positives on PDF, ZIP and Office files removed from the critical path, warnings still fire

**1.0**

- SHA-256 baselines, entropy detection, size trend, snapshots, restore, Excel reports, daily digest
- Desktop dashboard, 162 tests, CI on three Python versions

## Author

Egyan07, [github.com/Egyan07](https://github.com/Egyan07)

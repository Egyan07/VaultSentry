# 🛡 VaultSentry

### Backup Integrity Monitor for Windows

![GitHub stars](https://img.shields.io/github/stars/Egyan07/VaultSentry?style=social)
![GitHub forks](https://img.shields.io/github/forks/Egyan07/VaultSentry?style=social)
![GitHub issues](https://img.shields.io/github/issues/Egyan07/VaultSentry)
![GitHub last commit](https://img.shields.io/github/last-commit/Egyan07/VaultSentry)
![License](https://img.shields.io/github/license/Egyan07/VaultSentry)

**Built by Egyan**
| Red Parrot Accounting Ltd

VaultSentry is a **backup integrity monitoring system** designed to detect tampering, ransomware encryption, corruption, missing files, stale backups, and abnormal backup size drops.

The system automatically **hashes every file in backup storage**, stores a trusted baseline, and verifies the integrity of the entire backup set every night.

If anything suspicious occurs, VaultSentry **immediately alerts administrators and includes the issue in a daily digest report**.

---

# 🧰 Technology

Python 3
SQLite Database
Tkinter Desktop GUI
SMTP Email Alerts
Windows Task Scheduler

---

# ✨ Features

| Feature                      | Description                                    |
| ---------------------------- | ---------------------------------------------- |
| 🔐 SHA-256 Integrity Hashing | Cryptographically strong file verification     |
| 🧠 Entropy Analysis          | Detects ransomware encryption patterns         |
| 🛡 Tamper Detection          | Identifies modified or corrupted files         |
| 🚨 Ransom Note Detection     | Flags common ransomware note filenames         |
| 📉 Backup Size Monitoring    | Alerts if total backup size drops ≥30%         |
| 📂 Missing File Detection    | Detects deleted or moved backup files          |
| ⏳ Stale Backup Alerts        | Warns when newest backup exceeds threshold age |
| 📧 Email Alerts              | Immediate critical alerts + daily digest       |
| 📊 Excel Reports             | Multi-sheet colour-coded reports               |
| 📸 Baseline Snapshots        | Point-in-time baseline versions                |
| ♻ Restore Engine             | Restore files with folder structure            |
| 🖥 Desktop Dashboard         | Dark-mode monitoring GUI                       |
| 🔁 Scheduled Verification    | Automatic nightly verification                 |
| 🧪 Automated Tests           | 162 unit tests with CI pipeline                |

---

# 🚀 Installation

Run the installer as Administrator:

```cmd
right-click Install_VaultSentry.bat → Run as administrator
```

The installer will:

* install VaultSentry to
  `C:\SecurityLogs\VaultSentry\`

* create a **Windows scheduled task**

* generate the **initial integrity baseline**

---

# ⚡ Usage

Command line interface:

```cmd
python main.py --gui
python main.py --baseline
python main.py --verify
python main.py --snapshot "Before audit Mar 2026"
python main.py --list-snapshots
python main.py --restore
python main.py --digest
python main.py --report
python main.py --status
```

---

# 🖥 GUI Interface

VaultSentry includes a desktop monitoring dashboard.

| Tab       | Purpose                                      |
| --------- | -------------------------------------------- |
| Dashboard | Live stats, backup size trend, scan controls |
| Alerts    | Alert history with severity filtering        |
| Reports   | Generate and browse Excel reports            |
| Restore   | Restore files with preview plan              |
| Snapshots | Create, browse, diff, delete snapshots       |
| Settings  | Configuration viewer and diagnostics         |

---

# 📧 Email Alert System

VaultSentry supports both **instant alerts** and **daily digest reporting**.

**Immediate alerts**

Triggered instantly for critical events such as:

* ransomware suspected
* backup size drop
* missing backup files

Enable in `config.py`:

```python
EMAIL_ENABLED = True
```

**Daily digest**

A single HTML report summarising:

* last verification run
* all alerts in previous 25 hours
* backup system health

```python
DIGEST_ENABLED = True
DIGEST_TIME = 8
```

Store SMTP credentials securely as an environment variable:

```powershell
[System.Environment]::SetEnvironmentVariable(
'VAULTSENTRY_EMAIL_PASSWORD',
'your_app_password',
'Machine'
)
```

---

# 🏗 Architecture

```
VaultSentry
│
├── CLI + GUI (main.py)
│
├── Scanner Engine
│   ├ baseline hash creation
│   ├ nightly verification
│   ├ ransomware entropy detection
│   └ backup size analysis
│
├── Database Layer (SQLite)
│   ├ file hashes
│   ├ snapshots
│   ├ alert history
│   └ backup size trend
│
├── Alert System
│   ├ desktop alerts
│   ├ email notifications
│   └ alert deduplication
│
└── Reporting Engine
    ├ Excel reports
    ├ daily digest email
    └ system health summaries
```

---

# 🧠 Ransomware Detection

VaultSentry uses **Shannon entropy analysis** to detect encryption activity.

Normal files typically score:

```
4.0 – 6.5 entropy
```

Encrypted files typically score:

```
7.5 – 8.0 entropy
```

If a file's hash changes **AND entropy exceeds 7.8**, VaultSentry triggers:

```
CRITICAL: RANSOMWARE SUSPECTED
```

A second detection layer monitors **backup size trends**.

If total backup size drops **≥30% overnight**, VaultSentry generates another CRITICAL alert.

---

# 🧪 Testing

VaultSentry includes **162 automated unit tests**.

Run tests with:

```bash
pip install pytest pytest-cov
pytest tests/ -v
```

Current test coverage: **73%**

---

# 📂 Project Structure

```
VaultSentry
│
├ main.py
├ config.py
├ logger.py
├ Install_VaultSentry.bat
├ Uninstall_VaultSentry.bat
│
├ core
│   ├ database.py
│   ├ alerts.py
│   ├ scanner.py
│   ├ restore.py
│   ├ digest.py
│   └ reports.py
│
├ gui
│   ├ app.py
│   ├ theme.py
│   ├ tab_dashboard.py
│   ├ tab_alerts.py
│   ├ tab_reports.py
│   ├ tab_restore.py
│   ├ tab_snapshots.py
│   └ tab_settings.py
│
├ utils
│   └ file_utils.py
│
└ tests
```

---

# 🛣 Roadmap

Future improvements planned for VaultSentry:

* cloud backup monitoring (S3 / Backblaze)
* ransomware pattern learning
* web dashboard
* Slack / Teams alerts
* anomaly detection on backup trends
* cross-platform support (Linux)

---

# ⚠ Disclaimer

VaultSentry **detects backup integrity violations** but does not block ransomware or automatically restore data.

Any **CRITICAL alert should be treated as an immediate security incident.**

---

# 👨‍💻 Author

**Egyan07**

Developed for **Red Parrot Accounting Ltd**

---

# 🛡 VaultSentry

**Backup Integrity Monitoring. Ransomware Detection. Peace of Mind.**

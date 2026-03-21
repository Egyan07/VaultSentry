# =============================================================================
#   core/digest.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Daily email digest — one clean summary email per day instead of
#   individual per-alert emails for every issue.
#
#   Design:
#     build_digest_html(data)  — pure function, returns HTML string
#     build_digest_text(data)  — plain-text fallback
#     send_digest()            — fetches data, builds, and sends
#     should_send_digest()     — True if it's time and hasn't been sent today
#
#   Individual CRITICAL alerts still fire immediately via core/alerts.py.
#   The digest is a daily summary on top of that — not a replacement.
# =============================================================================

import os
import ssl
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import (
    APP_NAME, APP_VERSION,
    EMAIL_FROM, EMAIL_TO,
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
    DIGEST_ENABLED, DIGEST_TIME,
    DB_PATH,
)
from logger import log
from core.database import get_digest_data, get_setting, set_setting
from utils.file_utils import format_size


# =============================================================================
#   Digest state — persisted to SQLite so it survives process restarts
# =============================================================================

# FIX: replaced module-level _last_digest_date (lost on restart) with
# DB-persisted setting "last_digest_date" so the once-per-day guard works
# even when the scheduled task relaunches the process each night.


def should_send_digest(now: datetime | None = None) -> bool:
    """
    Return True if:
      - DIGEST_ENABLED is True
      - Current hour >= DIGEST_TIME
      - Digest has not already been sent today

    `now` can be injected for testing — defaults to datetime.now().
    """
    if not DIGEST_ENABLED:
        return False

    now = now or datetime.now()
    if now.hour < DIGEST_TIME:
        return False

    today_str        = now.strftime("%Y-%m-%d")
    last_digest_date = get_setting("last_digest_date", "")
    if last_digest_date == today_str:
        return False

    return True


def mark_digest_sent():
    """Persist today's date so duplicate digest sends are suppressed across restarts."""
    set_setting("last_digest_date", datetime.now().strftime("%Y-%m-%d"))


# =============================================================================
#   Build digest content
# =============================================================================

def build_digest_html(data: dict) -> str:
    """
    Build an HTML digest email from the data dict returned by get_digest_data().
    Pure function — no side effects, fully testable.
    """
    alerts   = data.get("alerts", [])
    last_run = data.get("last_run")
    stats    = data.get("stats", {})

    now_str  = datetime.now().strftime("%d %B %Y")

    # Colour map
    sev_colors = {
        "CRITICAL": "#ff4444",
        "WARNING":  "#f5a623",
        "INFO":     "#5bc0de",
    }

    # Overall status banner
    critical_count = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    warning_count  = sum(1 for a in alerts if a["severity"] == "WARNING")

    if critical_count > 0:
        banner_color = "#ff4444"
        banner_text  = f"⚠ {critical_count} CRITICAL ISSUE(S) REQUIRE ATTENTION"
    elif warning_count > 0:
        banner_color = "#f5a623"
        banner_text  = f"⚠ {warning_count} Warning(s) — Review Recommended"
    else:
        banner_color = "#00c97a"
        banner_text  = "✓ All Backups Verified — No Issues Found"

    # Scan summary rows
    scan_rows = ""
    if last_run:
        size_str = format_size(last_run.get("total_backup_size", 0))
        scan_rows = f"""
        <tr><td>Scan time</td><td>{last_run['run_time']}</td></tr>
        <tr><td>Files scanned</td><td>{last_run['files_scanned']}</td></tr>
        <tr><td>Files OK</td><td style="color:#00c97a">{last_run['files_ok']}</td></tr>
        <tr><td>Files changed</td><td style="color:{'#f5a623' if last_run['files_changed'] else '#888'}">{last_run['files_changed']}</td></tr>
        <tr><td>Files missing</td><td style="color:{'#ff4444' if last_run['files_missing'] else '#888'}">{last_run['files_missing']}</td></tr>
        <tr><td>Alerts raised</td><td style="color:{'#ff4444' if last_run['alerts_raised'] else '#888'}">{last_run['alerts_raised']}</td></tr>
        <tr><td>Total backup size</td><td>{size_str}</td></tr>
        <tr><td>Duration</td><td>{last_run['duration_secs']:.1f}s</td></tr>
        """
    else:
        scan_rows = "<tr><td colspan='2'>No scan runs found</td></tr>"

    # Alert rows
    alert_rows = ""
    if alerts:
        for alert in alerts[:50]:  # cap at 50 in email
            sev   = alert["severity"]
            color = sev_colors.get(sev, "#888")
            fp    = alert["filepath"]
            # Truncate long paths
            if len(fp) > 80:
                fp = "..." + fp[-77:]
            det = (alert["details"] or "")[:200].replace("\n", " ")
            alert_rows += f"""
            <tr>
              <td style="color:{color};font-weight:bold">{sev}</td>
              <td>{alert['timestamp']}</td>
              <td>{alert['alert_type']}</td>
              <td style="font-family:monospace;font-size:11px">{fp}</td>
              <td style="font-size:11px;color:#aaa">{det}</td>
            </tr>"""
    else:
        alert_rows = "<tr><td colspan='5' style='color:#888'>No alerts in the last 25 hours</td></tr>"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body      {{ font-family: Consolas, monospace; background:#0d1b2a; color:#e8f0fe; margin:0; padding:20px; }}
  .card     {{ background:#1a2d42; border-radius:6px; padding:20px; margin-bottom:16px; }}
  .banner   {{ background:{banner_color}22; border-left:4px solid {banner_color};
               padding:12px 16px; border-radius:4px; margin-bottom:16px; color:{banner_color};
               font-size:15px; font-weight:bold; }}
  h1        {{ color:#2a7fff; font-size:20px; margin:0 0 4px 0; }}
  h2        {{ color:#8faac7; font-size:13px; margin:0 0 16px 0; font-weight:normal; }}
  h3        {{ color:#2a7fff; font-size:14px; margin:0 0 12px 0; }}
  table     {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th        {{ background:#112233; color:#8faac7; padding:8px 10px; text-align:left;
               border-bottom:1px solid #1e3a5f; }}
  td        {{ padding:7px 10px; border-bottom:1px solid #1a2d42; color:#e8f0fe; }}
  tr:hover  {{ background:#1e3a5f22; }}
  .footer   {{ color:#4a6080; font-size:11px; margin-top:20px; text-align:center; }}
</style>
</head>
<body>
  <h1>🛡 {APP_NAME} v{APP_VERSION} — Daily Digest</h1>
  <h2>Red Parrot Accounting Ltd &nbsp;|&nbsp; {now_str}</h2>

  <div class="banner">{banner_text}</div>

  <div class="card">
    <h3>Last Scan Summary</h3>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      {scan_rows}
    </table>
  </div>

  <div class="card">
    <h3>Alerts (last 25 hours) — {len(alerts)} total</h3>
    <table>
      <tr>
        <th>Severity</th>
        <th>Time</th>
        <th>Alert Type</th>
        <th>File</th>
        <th>Details</th>
      </tr>
      {alert_rows}
    </table>
    {"<p style='color:#888;font-size:11px'>Showing first 50 alerts. Check VaultSentry for full history.</p>" if len(alerts) > 50 else ""}
  </div>

  <p class="footer">
    Automated digest from {APP_NAME} v{APP_VERSION} · Red Parrot Accounting Ltd ·
    Investigate any CRITICAL alerts immediately under GDPR/ICO obligations.
  </p>
</body>
</html>"""

    return html


def build_digest_text(data: dict) -> str:
    """
    Plain-text fallback for email clients that don't render HTML.
    Pure function — fully testable.
    """
    alerts   = data.get("alerts", [])
    last_run = data.get("last_run")
    now_str  = datetime.now().strftime("%d %B %Y %H:%M")

    critical = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    warning  = sum(1 for a in alerts if a["severity"] == "WARNING")

    lines = [
        f"{APP_NAME} v{APP_VERSION} — Daily Digest",
        f"Red Parrot Accounting Ltd | {now_str}",
        "=" * 60,
    ]

    if critical > 0:
        lines.append(f"STATUS: {critical} CRITICAL ISSUE(S) REQUIRE ATTENTION")
    elif warning > 0:
        lines.append(f"STATUS: {warning} Warning(s) — Review Recommended")
    else:
        lines.append("STATUS: All backups verified — no issues found")

    lines += ["", "LAST SCAN SUMMARY", "-" * 40]
    if last_run:
        lines += [
            f"  Scan time    : {last_run['run_time']}",
            f"  Files scanned: {last_run['files_scanned']}",
            f"  Files OK     : {last_run['files_ok']}",
            f"  Changed      : {last_run['files_changed']}",
            f"  Missing      : {last_run['files_missing']}",
            f"  Alerts       : {last_run['alerts_raised']}",
            f"  Backup size  : {format_size(last_run.get('total_backup_size', 0))}",
            f"  Duration     : {last_run['duration_secs']:.1f}s",
        ]
    else:
        lines.append("  No scan runs found")

    lines += ["", f"ALERTS (last 25h) — {len(alerts)} total", "-" * 40]
    if alerts:
        for a in alerts[:50]:
            lines.append(
                f"  [{a['severity']}] {a['timestamp']} — {a['alert_type']}"
            )
            lines.append(f"    File: {a['filepath']}")
            if a.get("details"):
                lines.append(f"    {a['details'][:120]}")
    else:
        lines.append("  No alerts in the last 25 hours")

    lines += [
        "",
        "=" * 60,
        f"Automated digest from {APP_NAME} · Red Parrot Accounting Ltd",
    ]

    return "\n".join(lines)


# =============================================================================
#   Send
# =============================================================================

def send_digest(since_hours: int = 25) -> bool:
    """
    Fetch digest data, build email, and send.
    Returns True on success, False on failure.
    """
    pwd = os.environ.get("VAULTSENTRY_EMAIL_PASSWORD", "")
    if not pwd:
        log.warning("digest: VAULTSENTRY_EMAIL_PASSWORD not set — digest skipped")
        return False

    data = get_digest_data(since_hours)

    html_body = build_digest_html(data)
    text_body = build_digest_text(data)

    alerts    = data.get("alerts", [])
    critical  = sum(1 for a in alerts if a["severity"] == "CRITICAL")

    subject = (
        f"[{APP_NAME}] Daily Digest — "
        f"{'⚠ ' + str(critical) + ' CRITICAL' if critical else '✓ All Clear'} "
        f"— {datetime.now().strftime('%d %b %Y')}"
    )

    msg             = MIMEMultipart("alternative")
    msg["From"]     = EMAIL_FROM
    msg["To"]       = EMAIL_TO
    msg["Subject"]  = subject

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html",  "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(EMAIL_FROM, pwd)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        mark_digest_sent()
        log.info("Daily digest sent to %s (%d alerts)", EMAIL_TO, len(alerts))
        return True

    except smtplib.SMTPAuthenticationError as e:
        log.error("digest: SMTP auth failed: %s", e)
    except smtplib.SMTPException as e:
        log.error("digest: SMTP error: %s", e)
    except Exception as e:
        log.error("digest: unexpected error: %s", e)

    return False

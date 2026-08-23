"""
Usage & Upsell Analyst — SKOOLED-AI's usage-nudge agent.

Run via cron (standalone, not part of the live web app): checks every
free-plan teacher's usage this month and sends two kinds of warm,
non-pushy nudges — never more than one of each per user per period,
tracked in email_nudges so re-running this script is always safe.

  - near_cap: teacher has used all or all-but-one of their free
    generations this month. Leads with what they've accomplished;
    mentions Pro only after that, and says explicitly there's no
    pressure — free resets next month regardless.
  - dormant: teacher generated at least one lesson before, but hasn't
    touched the generator in 30+ days. Re-engagement, not a sales
    pitch — never sent to someone who's never generated anything.

Fails open per-user: one broken row never stops the rest of the batch.
send_email() itself never raises, so a broken mail server just means
zero nudges get recorded as sent (they'll be retried next run) rather
than a crashed job.

Usage: python3 usage_nudge_agent.py
Suggested cron: once daily — near-cap nudges are time-sensitive, a
teacher who hits their cap should hear from you same-day.
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from auth import get_db, send_email
from billing import FREE_MONTHLY_CAP, get_monthly_usage

APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://skooled-ai.webprvw.xyz").rstrip("/")
UPGRADE_URL = f"{APP_BASE_URL}/account/upgrade"
GENERATOR_URL = f"{APP_BASE_URL}/generator"


def _already_sent(cur, user_id, nudge_type, period_key):
    cur.execute(
        "SELECT 1 FROM email_nudges WHERE user_id=%s AND nudge_type=%s AND period_key=%s",
        (user_id, nudge_type, period_key),
    )
    return cur.fetchone() is not None


def _record_sent(cur, user_id, nudge_type, period_key):
    cur.execute(
        "INSERT IGNORE INTO email_nudges (user_id, nudge_type, period_key) VALUES (%s, %s, %s)",
        (user_id, nudge_type, period_key),
    )


def _near_cap_email(name, usage, cap):
    subject = "You've been busy this month!"
    body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px;">
      <h2 style="color:#1e293b;margin-bottom:8px;">Nice work, {name}!</h2>
      <p style="color:#475569;">You've generated <strong>{usage} lesson plan{'s' if usage != 1 else ''}</strong> this month — that's real time back for your students.</p>
      <p style="color:#475569;">You've used {usage} of your {cap} free generations this month. If you'd like unlimited generations for the rest of the month (and beyond), Pro is just &#8369;299/month.</p>
      <a href="{UPGRADE_URL}" style="display:inline-block;margin:20px 0;padding:12px 28px;background:#ff5f57;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">See Pro &rarr;</a>
      <p style="color:#94a3b8;font-size:12px;">No pressure at all — your free generations reset next month either way.</p>
    </div>
    """
    return subject, body


def _dormant_email(name):
    subject = "New curriculum standards are live on SKOOLED-AI"
    body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px;">
      <h2 style="color:#1e293b;margin-bottom:8px;">We've missed you, {name}!</h2>
      <p style="color:#475569;">Since you last generated a lesson, SKOOLED-AI added support for Common Core, UK National Curriculum, ACARA, and IB — not just MATATAG.</p>
      <p style="color:#475569;">If you've got two minutes, come try your next lesson plan.</p>
      <a href="{GENERATOR_URL}" style="display:inline-block;margin:20px 0;padding:12px 28px;background:#ff5f57;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Open the Generator &rarr;</a>
    </div>
    """
    return subject, body


def run():
    period_key = datetime.utcnow().strftime("%Y-%m")
    dormant_cutoff = datetime.utcnow() - timedelta(days=30)

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, email FROM users WHERE plan='free' AND status='approved'")
            free_users = cur.fetchall()
    finally:
        conn.close()

    near_cap_sent = 0
    dormant_sent = 0
    errors = 0

    for user in free_users:
        try:
            usage = get_monthly_usage(user["id"])
        except Exception as e:
            print(f"[usage_nudge] Could not read usage for user {user['id']}: {e}")
            errors += 1
            continue

        conn = get_db()
        try:
            with conn.cursor() as cur:
                if usage >= FREE_MONTHLY_CAP - 1 and not _already_sent(cur, user["id"], "near_cap", period_key):
                    subject, body = _near_cap_email(user["name"], usage, FREE_MONTHLY_CAP)
                    if send_email(user["email"], subject, body):
                        _record_sent(cur, user["id"], "near_cap", period_key)
                        near_cap_sent += 1

                if usage == 0:
                    cur.execute(
                        """SELECT MAX(created_at) AS last_gen FROM activity_log
                           WHERE user_id=%s AND action_type IN ('lesson_generate','topic_generate')""",
                        (user["id"],),
                    )
                    row = cur.fetchone()
                    last_gen = row["last_gen"] if row else None
                    if last_gen and last_gen < dormant_cutoff and not _already_sent(cur, user["id"], "dormant", period_key):
                        subject, body = _dormant_email(user["name"])
                        if send_email(user["email"], subject, body):
                            _record_sent(cur, user["id"], "dormant", period_key)
                            dormant_sent += 1
        except Exception as e:
            print(f"[usage_nudge] Error processing user {user['id']}: {e}")
            errors += 1
        finally:
            conn.close()

    print(f"[usage_nudge] Done. near_cap={near_cap_sent} dormant={dormant_sent} errors={errors} (of {len(free_users)} free users checked)")


if __name__ == "__main__":
    run()

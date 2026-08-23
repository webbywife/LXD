"""
Billing and usage-cap logic for SKOOLED-AI.

Free tier is capped on generation volume, not features — every teacher gets
the full product to try. Cap is computed live from activity_log for the
current calendar month, so there's no separate counter to reset or drift.

Checkout is via PayMongo (GCash/Maya/card — matches the PH teacher user
base). NOT YET LIVE-TESTED: this needs a real PayMongo secret key and
webhook signing secret (from a merchant account only the site owner can
create) before it can process a real payment. Until PAYMONGO_SECRET_KEY
is set, paymongo_configured() returns False and callers fall back to a
manual "email to upgrade" path — see /account/upgrade in app.py.
"""

import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta

import requests

from auth import get_db

PAYMONGO_API_BASE = "https://api.paymongo.com/v1"
PRO_PLAN_DAYS = 30

FREE_MONTHLY_CAP = 5
PRO_MONTHLY_PRICE_PHP = 299

# Each of these represents one "lesson plan generated" from the teacher's
# point of view, whether it came from curriculum mode or topic mode.
GENERATION_ACTIONS = ("lesson_generate", "topic_generate")


def get_user_plan(user_id):
    """Return the user's effective plan, auto-downgrading an expired Pro plan to free."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT plan, plan_expires_at FROM users WHERE id = %s", (user_id,)
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return "free", None

    plan = row["plan"]
    expires_at = row["plan_expires_at"]
    if plan == "pro" and expires_at and expires_at < datetime.utcnow():
        plan = "free"
    return plan, expires_at


def get_monthly_usage(user_id):
    """Count this calendar month's lesson-plan generations for a user."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(GENERATION_ACTIONS))
            cur.execute(
                f"""SELECT COUNT(*) AS cnt FROM activity_log
                    WHERE user_id = %s
                    AND action_type IN ({placeholders})
                    AND created_at >= DATE_FORMAT(NOW(), '%%Y-%%m-01')""",
                (user_id, *GENERATION_ACTIONS),
            )
            return cur.fetchone()["cnt"]
    finally:
        conn.close()


def check_generation_allowed(user_id):
    """Return (allowed, usage_count, cap, plan) for a generation request.

    Pro users are always allowed (cap=None). Free users are allowed up to
    FREE_MONTHLY_CAP generations this calendar month.

    Fails OPEN: if the DB is unreachable or errors, this allows the
    generation rather than blocking every teacher's lesson plan over an
    unrelated infrastructure hiccup. Worst case is a little free usage
    slipping through during an outage — never a broken core product.
    """
    try:
        plan, _ = get_user_plan(user_id)
        if plan == "pro":
            return True, None, None, plan
        usage = get_monthly_usage(user_id)
        return usage < FREE_MONTHLY_CAP, usage, FREE_MONTHLY_CAP, plan
    except Exception:
        return True, None, None, "free"


# ── PayMongo checkout ───────────────────────────────────────────

def paymongo_configured():
    return bool(os.environ.get("PAYMONGO_SECRET_KEY"))


def create_checkout_session(user_id, user_email, success_url, cancel_url):
    """Create a PayMongo Checkout Session for one month of Pro.

    Returns (checkout_url, error). The webhook (see handle_paymongo_webhook)
    is what actually grants the plan on payment — this only starts checkout.
    """
    secret_key = os.environ.get("PAYMONGO_SECRET_KEY", "")
    if not secret_key:
        return None, "Payments aren't configured yet."

    payload = {
        "data": {
            "attributes": {
                "send_email_receipt": True,
                "show_description": True,
                "show_line_items": True,
                "description": "SKOOLED-AI Pro — 1 month",
                "line_items": [{
                    "currency": "PHP",
                    "amount": PRO_MONTHLY_PRICE_PHP * 100,  # centavos
                    "name": "SKOOLED-AI Pro (1 month, unlimited generations)",
                    "quantity": 1,
                }],
                "payment_method_types": ["gcash", "card", "paymaya"],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"user_id": str(user_id), "user_email": user_email},
            }
        }
    }

    try:
        resp = requests.post(
            f"{PAYMONGO_API_BASE}/checkout_sessions",
            json=payload,
            auth=(secret_key, ""),
            timeout=15,
        )
        resp.raise_for_status()
        checkout_url = resp.json()["data"]["attributes"]["checkout_url"]
        return checkout_url, None
    except Exception as e:
        return None, f"Could not start checkout: {e}"


def verify_paymongo_signature(raw_body, signature_header, webhook_secret, live_mode=False):
    """Verify the Paymongo-Signature header per PayMongo's HMAC scheme.

    Header format: "t=<timestamp>,te=<test_sig>,li=<live_sig>". We recompute
    HMAC-SHA256 over "{t}.{raw_body}" using the webhook's signing secret and
    compare against the test or live signature depending on which key set
    triggered the event.
    """
    if not signature_header or not webhook_secret:
        return False

    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    timestamp = parts.get("t")
    expected_sig = parts.get("li") if live_mode else parts.get("te")
    if not timestamp or not expected_sig:
        return False

    signed_payload = f"{timestamp}.{raw_body.decode() if isinstance(raw_body, bytes) else raw_body}"
    computed_sig = hmac.new(
        webhook_secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_sig, expected_sig)


def activate_pro_plan(user_id):
    """Grant Pro for PRO_PLAN_DAYS, extending from the current expiry if still active."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT plan, plan_expires_at FROM users WHERE id = %s", (user_id,)
            )
            row = cur.fetchone()
            if not row:
                return False

            now = datetime.utcnow()
            current_expiry = row["plan_expires_at"]
            base = current_expiry if (row["plan"] == "pro" and current_expiry and current_expiry > now) else now
            new_expiry = base + timedelta(days=PRO_PLAN_DAYS)

            cur.execute(
                "UPDATE users SET plan = 'pro', plan_expires_at = %s WHERE id = %s",
                (new_expiry, user_id),
            )
        return True
    finally:
        conn.close()

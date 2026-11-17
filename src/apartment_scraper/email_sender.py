import os
import uuid
import httpx


def rejection_reason(response):
    """Return actionable diagnostics without exposing provider bodies or addresses."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    name = body.get("name")
    safe_names = {
        "validation_error", "missing_api_key", "invalid_api_key", "restricted_api_key",
        "rate_limit_exceeded", "monthly_quota_exceeded", "daily_quota_exceeded",
        "application_error", "invalid_from_address", "invalid_to_address",
    }
    code = name if isinstance(name, str) and name in safe_names else "unclassified_error"
    message = str(body.get("message", "")).lower()
    # Classify the message, but never echo it: it can contain email addresses.
    if "testing emails" in message or "your own email" in message:
        hint = "Resend test mode restricts recipients; use your Resend account email or verify a sender domain."
    elif "domain" in message and ("not verified" in message or "verify" in message):
        hint = "Verify the sender domain in Resend and use that domain in REPORT_EMAIL_FROM."
    elif "api_key" in code or response.status_code == 401:
        hint = "Replace RESEND_API_KEY with a valid sending key authorized for the sender domain."
    elif "quota" in code or response.status_code == 429:
        hint = "Check the Resend quota and rate limits before rerunning."
    elif response.status_code == 403:
        hint = "Check sender-domain verification, key permissions and test-mode recipient restrictions."
    elif response.status_code in (400, 422):
        hint = "Check REPORT_EMAIL_FROM and REPORT_EMAIL_TO are single valid email addresses."
    else:
        hint = "Inspect the Resend dashboard for the rejected request."
    return f"Email provider rejected delivery: HTTP {response.status_code}, {code}. {hint}"


def send(subject, html, text):
    values = {k: os.environ.get(k, "").strip() for k in ("RESEND_API_KEY", "REPORT_EMAIL_TO", "REPORT_EMAIL_FROM")}
    if not all(values.values()):
        raise RuntimeError("Missing required email environment variables")
    # One API request: no ambiguous duplicate deliveries after a timeout.
    try:
        response = httpx.post("https://api.resend.com/emails", timeout=30,
            headers={"Authorization": "Bearer " + values["RESEND_API_KEY"], "Idempotency-Key": str(uuid.uuid4())},
            json={"from": values["REPORT_EMAIL_FROM"], "to": [values["REPORT_EMAIL_TO"]],
                  "subject": subject, "html": html, "text": text})
    except httpx.HTTPError:
        raise RuntimeError("Email delivery failed; inspect provider dashboard before retrying") from None
    if response.status_code not in (200, 201):
        raise RuntimeError(rejection_reason(response))
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not body.get("id"):
        raise RuntimeError("Email provider returned an invalid success response; check dashboard before retrying")

import os
import uuid
import httpx

def send(subject, html, text):
    values = {k: os.environ.get(k, "") for k in ("RESEND_API_KEY", "REPORT_EMAIL_TO", "REPORT_EMAIL_FROM")}
    if not all(values.values()):
        raise RuntimeError("Missing required email environment variables")
    # One API request: no ambiguous duplicate deliveries after a timeout.
    try:
        response = httpx.post("https://api.resend.com/emails", timeout=30,
            headers={"Authorization": "Bearer " + values["RESEND_API_KEY"], "Idempotency-Key": str(uuid.uuid4())},
            json={"from": values["REPORT_EMAIL_FROM"], "to": [values["REPORT_EMAIL_TO"]],
                  "subject": subject, "html": html, "text": text})
        if response.status_code not in (200, 201) or not response.json().get("id"):
            raise RuntimeError("Email provider rejected delivery")
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("Email delivery failed; inspect provider dashboard") from None

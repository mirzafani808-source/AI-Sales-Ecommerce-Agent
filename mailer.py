"""
Email helper — works on VS Code / local Python via Gmail SMTP.

Setup (Gmail):
  1. Go to https://myaccount.google.com/apppasswords
  2. Create an App Password for "Mail"
  3. Add to your .env file:
       SMTP_HOST=smtp.gmail.com
       SMTP_PORT=587
       SMTP_USE_TLS=true
       SMTP_USER=you@gmail.com
       SMTP_PASS=xxxx xxxx xxxx xxxx   (16-char App Password)
       SMTP_FROM=you@gmail.com
       OWNER_EMAIL=owner@yourstore.com

If SMTP is not configured, emails are silently skipped — the app keeps working.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# Owner email comes from OWNER_EMAIL env var only
OWNER_EMAILS = []


# ---------------------------------------------------------------------------
# Core send function (SMTP only)
# ---------------------------------------------------------------------------

def send_email(to_email: str, subject: str, html: str) -> dict:
    """Send an HTML email via SMTP.
    Returns {"sent": True/False, "via": "smtp"/None, ...}
    If SMTP is not configured, returns sent=False without crashing.
    """
    if not to_email:
        return {"sent": False, "via": None, "reason": "no recipient"}

    host = os.environ.get("SMTP_HOST", "").strip()
    print(f"DEBUG: SMTP_HOST = {repr(host)}")  # DEBUG
    if not host:
        logger.info(
            "Email skipped (SMTP not configured). "
            "Add SMTP_HOST / SMTP_USER / SMTP_PASS to your .env to enable emails."
        )
        return {"sent": False, "via": None, "reason": "SMTP not configured"}

    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    sender   = os.environ.get("SMTP_FROM", user or "noreply@example.com").strip()
    use_tls  = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user:
                server.login(user, password)
            server.sendmail(sender, [to_email], msg.as_string())
        logger.info(f"Email sent via SMTP to {to_email}")
        return {"sent": True, "via": "smtp"}
    except Exception as e:
        logger.warning(f"SMTP send failed to {to_email}: {e}")
        return {"sent": False, "via": None, "reason": str(e)}


# ---------------------------------------------------------------------------
# Email HTML templates
# ---------------------------------------------------------------------------

def _build_item_rows(items) -> str:
    rows = ""
    for it in items:
        rows += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;'>{it.product_name}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center;'>{it.quantity}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;'>${it.price * it.quantity:.2f}</td>"
            f"</tr>"
        )
    return rows


def _customer_confirmation_html(order, items) -> str:
    rows = _build_item_rows(items)
    phone_line = (
        f'<p style="margin:4px 0;color:#555;">Phone: {order.customer_phone}</p>'
        if order.customer_phone else ""
    )
    return f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;background:#fff;color:#222;">
  <div style="background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;padding:28px;border-radius:12px 12px 0 0;text-align:center;">
    <h1 style="margin:0;font-size:26px;">&#10003; Order Confirmed!</h1>
    <p style="margin:8px 0 0;opacity:0.9;font-size:15px;">Thank you for your purchase, {order.customer_name}!</p>
  </div>
  <div style="padding:28px;">
    <div style="background:#f9f7ff;border-radius:10px;padding:16px;margin-bottom:22px;border-left:4px solid #6366f1;">
      <p style="margin:0;color:#555;font-size:14px;">Your order <b style="color:#6366f1;">#{order.id}</b> has been received and is being processed.</p>
    </div>

    <h3 style="color:#333;margin-bottom:12px;">Order Summary</h3>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#f4f4f8;">
          <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555;">Product</th>
          <th style="padding:10px 8px;text-align:center;font-size:13px;color:#555;">Qty</th>
          <th style="padding:10px 8px;text-align:right;font-size:13px;color:#555;">Total</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <table style="width:100%;margin-top:16px;border-top:2px solid #f0f0f0;padding-top:12px;">
      <tr><td style="padding:6px 0;color:#666;">Subtotal</td><td style="text-align:right;color:#333;">${order.subtotal:.2f}</td></tr>
      <tr><td style="padding:6px 0;color:#666;">Delivery</td><td style="text-align:right;color:#333;">${order.delivery_fee:.2f}</td></tr>
      <tr style="font-size:16px;font-weight:700;">
        <td style="padding:8px 0;color:#222;">Total Paid</td>
        <td style="text-align:right;color:#6366f1;">${order.total:.2f}</td>
      </tr>
    </table>

    <div style="margin-top:24px;background:#f9f7ff;border-radius:10px;padding:16px;">
      <h4 style="margin:0 0 10px;color:#333;">Delivery Address</h4>
      <p style="margin:4px 0;color:#555;">{order.customer_address}</p>
      {phone_line}
    </div>

    <p style="color:#888;font-size:13px;margin-top:24px;text-align:center;">
      We'll notify you when your order ships. Questions? Reply to this email.
    </p>
  </div>
  <div style="background:#f4f4f8;padding:14px;text-align:center;border-radius:0 0 12px 12px;">
    <p style="margin:0;color:#aaa;font-size:12px;">AI Sales Agent &mdash; Automated order confirmation</p>
  </div>
</div>
"""


def _owner_notification_html(order, items) -> str:
    rows = _build_item_rows(items)
    return f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;background:#fff;color:#222;">
  <div style="background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;padding:24px;border-radius:12px 12px 0 0;">
    <h2 style="margin:0;">&#128722; New Order #{order.id}</h2>
    <p style="margin:4px 0 0;opacity:0.85;">Status: {order.status} &mdash; Total: ${order.total:.2f}</p>
  </div>
  <div style="padding:24px;">
    <h3 style="margin-top:0;">Customer Details</h3>
    <p style="margin:4px 0;"><b>Name:</b> {order.customer_name}</p>
    <p style="margin:4px 0;"><b>Email:</b> {order.customer_email}</p>
    <p style="margin:4px 0;"><b>Phone:</b> {order.customer_phone or '&mdash;'}</p>
    <p style="margin:4px 0;"><b>Address:</b> {order.customer_address}</p>

    <h3>Items Ordered</h3>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#f4f4f8;">
          <th style="padding:8px;text-align:left;">Product</th>
          <th style="padding:8px;text-align:center;">Qty</th>
          <th style="padding:8px;text-align:right;">Total</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <table style="width:100%;margin-top:18px;">
      <tr><td>Subtotal</td><td style="text-align:right;">${order.subtotal:.2f}</td></tr>
      <tr><td>Delivery</td><td style="text-align:right;">${order.delivery_fee:.2f}</td></tr>
      <tr><td><b>Total</b></td><td style="text-align:right;"><b>${order.total:.2f}</b></td></tr>
    </table>

    <p style="color:#888;font-size:12px;margin-top:24px;">
      Fraud risk score: {order.fraud_score:.2f} &mdash; Sent by AI Sales Agent
    </p>
  </div>
</div>
"""


def _contact_html(name: str, sender_email: str, subject: str, message: str) -> str:
    return f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;background:#fff;color:#222;">
  <div style="background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;padding:24px;border-radius:12px 12px 0 0;">
    <h2 style="margin:0;">&#9993; New Customer Message</h2>
    <p style="margin:6px 0 0;opacity:0.85;">Subject: {subject or '(no subject)'}</p>
  </div>
  <div style="padding:24px;">
    <p style="margin:6px 0;"><b>From:</b> {name} &lt;{sender_email}&gt;</p>
    <p style="margin:6px 0;"><b>Subject:</b> {subject or '&mdash;'}</p>
    <hr style="border:none;border-top:1px solid #eee;margin:18px 0;">
    <div style="background:#f9f7ff;border-radius:10px;padding:18px;line-height:1.7;white-space:pre-wrap;">{message}</div>
    <p style="color:#aaa;font-size:12px;margin-top:24px;">
      Reply directly to this email to respond to the customer.
    </p>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_order_confirmation(order, items) -> dict:
    """
    Send two emails after a successful order:
      1. Customer confirmation  → order.customer_email
      2. Owner notification     → OWNER_EMAIL env var (if set)

    Returns {"sent": True/False, "via": "smtp"/None, "customer": bool, "owner": bool}
    """
    result = {"sent": False, "via": None, "customer": False, "owner": False}

    customer_html = _customer_confirmation_html(order, items)
    r = send_email(
        order.customer_email,
        f"Your Order #{order.id} is Confirmed! \U0001f389",
        customer_html,
    )
    result["customer"] = r.get("sent", False)
    if r.get("sent"):
        result["sent"] = True
        result["via"]  = r.get("via")

    owner_email = os.environ.get("OWNER_EMAIL", "").strip()
    if owner_email and owner_email.lower() != order.customer_email.lower():
        owner_html = _owner_notification_html(order, items)
        r2 = send_email(owner_email, f"New Order #{order.id} \u2014 ${order.total:.2f}", owner_html)
        result["owner"] = r2.get("sent", False)
        if r2.get("sent") and not result["sent"]:
            result["sent"] = True
            result["via"]  = r2.get("via")

    if not result["sent"]:
        result["reason"] = "SMTP not configured — add SMTP_HOST/USER/PASS to .env"

    return result


def send_contact_message(name: str, sender_email: str, subject: str, message: str) -> dict:
    """Forward a contact form submission to all owner emails."""
    recipients = list(OWNER_EMAILS)
    env_owner = os.environ.get("OWNER_EMAIL", "").strip()
    if env_owner and env_owner not in recipients:
        recipients.append(env_owner)

    html = _contact_html(name, sender_email, subject, message)
    results = []
    for rcpt in recipients:
        r = send_email(rcpt, f"Customer Message: {subject or name}", html)
        results.append(r.get("sent", False))

    sent = any(results)
    return {
        "sent": sent,
        "recipients": len(recipients),
        "via": "smtp" if sent else None,
        "reason": None if sent else "SMTP not configured",
    }

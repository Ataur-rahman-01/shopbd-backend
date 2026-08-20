"""
Bangladesh bulk SMS integration.
Works with common BD SMS gateways: BulkSMSBD, GreenWeb, SMSNOC, etc.

Admin configures:
  sms_api_url  — provider's API endpoint (e.g. https://bulksmsbd.net/api/smsapi)
  sms_api_key  — API key / token
  sms_sender_id — approved sender ID (max 11 chars)

If any of these are missing, SMS is silently skipped (no error, no crash).
"""

import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger("shopbd.sms")


class SmsError(Exception):
    """SMS sending failed."""


def sms_is_configured(settings) -> bool:
    """Check if all SMS credentials are provided."""
    return bool(
        settings.sms_api_url
        and settings.sms_api_url.strip()
        and settings.sms_api_key
        and settings.sms_api_key.strip()
        and settings.sms_sender_id
        and settings.sms_sender_id.strip()
    )


def send_sms(settings, phone: str, message: str) -> bool:
    """
    Send an SMS to a Bangladeshi phone number.

    Phone should be in 01XXXXXXXXX format (auto-converts to 8801XXXXXXXXX
    if the API URL contains 'bulksmsbd' which expects that format).

    Returns True on success. Raises SmsError on failure.
    Silently returns False if SMS is not configured.
    """
    if not sms_is_configured(settings):
        logger.info("SMS not configured — skipping SMS to %s", phone)
        return False

    api_url = settings.sms_api_url.strip()
    api_key = settings.sms_api_key.strip()
    sender_id = settings.sms_sender_id.strip()

    # Clean phone number: strip +88/88 prefix, ensure it starts with 0
    number = phone.strip().replace("+88", "").replace(" ", "")
    if number.startswith("88"):
        number = "0" + number[2:]

    # Some providers (like BulkSMSBD) expect 8801XXXXXXXXX format
    if "bulksmsbd" in api_url.lower():
        if number.startswith("0"):
            number = "88" + number[1:]

    try:
        # Try POST with form-encoded body (most common BD format)
        params = {
            "api_key": api_key,
            "type": "text",
            "number": number,
            "senderid": sender_id,
            "message": message,
        }
        data = urlencode(params).encode("utf-8")
        req = Request(api_url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status

        if status != 200:
            raise SmsError(f"SMS API returned HTTP {status}: {body[:200]}")

        # Check common error patterns in response
        body_lower = body.lower()
        if "error" in body_lower and "success" not in body_lower:
            # Some providers return HTTP 200 even on error
            raise SmsError(f"SMS API error: {body[:200]}")

        logger.info("SMS sent to %s: %s", phone, body[:100])
        return True

    except URLError as exc:
        raise SmsError(f"SMS API unreachable: {exc}") from exc
    except Exception as exc:
        raise SmsError(f"SMS sending failed: {exc}") from exc


def send_order_confirmation_sms(settings, order) -> bool:
    """
    Send a confirmation SMS when an order is confirmed by admin.

    Uses the customizable `sms_confirmation_template` from Settings with
    placeholders replaced:
      {brand} → brand name
      {id}    → order id
      {items} → product list ("Name x2, Other x1")
      {total} → order total in taka (formatted: 1,500)
    Falls back to a sensible Bangla default if the template is empty.
    """
    brand = settings.brand_name or "ShopBD"
    if settings.sms_confirmation_template and settings.sms_confirmation_template.strip():
        template = settings.sms_confirmation_template.strip()
    else:
        template = "{brand}: আপনার অর্ডার #{id} কনফার্ম হয়েছে।\n{items}\nমোট: ৳{total:,.0f} (ক্যাশ অন ডেলিভারি)\nশীঘ্রই ডেলিভারি দেওয়া হবে。"

    items = ", ".join(f"{i.product_name} x{i.qty}" for i in order.items)
    if len(items) > 80:
        items = items[:77] + "..."

    try:
        message = template.format(brand=brand, id=order.id, items=items, total=order.total)
    except (KeyError, ValueError, IndexError):
        # Fall back to default if the admin entered an invalid template
        message = f"{brand}: আপনার অর্ডার #{order.id} কনফার্ম হয়েছে।\n{items}\nমোট: ৳{order.total:,.0f} (ক্যাশ অন ডেলিভারি)\nশীঘ্রই ডেলিভারি দেওয়া হবে。"

    return send_sms(settings, order.phone, message)
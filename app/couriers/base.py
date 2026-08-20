"""Shared courier client plumbing."""

# Bengali digit -> ASCII digit (admins/customers often type Bengali numerals)
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


class CourierError(Exception):
    """Any courier API failure — bad credentials, validation, network, timeout."""


def normalize_bd_phone(phone: str) -> str:
    """Normalize a Bangladeshi phone to 11-digit 01XXXXXXXXX form.

    Handles +880/880 prefixes and Bengali digits. Raises CourierError when
    the result cannot be a valid BD mobile number.
    """
    digits = (phone or "").translate(_BN_DIGITS)
    digits = "".join(c for c in digits if c.isdigit())
    if digits.startswith("880") and len(digits) == 13:
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    if len(digits) != 11 or not digits.startswith("01"):
        raise CourierError(f"Invalid recipient phone number: {phone!r}")
    return digits

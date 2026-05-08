import re


def normalize_phone_number(value: str) -> str:
    """Return a stable phone key for duplicate checks without changing display text."""
    if not value:
        return ""
    digits = re.sub(r"\D+", "", value)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits

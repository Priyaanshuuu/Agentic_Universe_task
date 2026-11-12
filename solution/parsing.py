from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable


_HEADER_SEPARATOR_RE = re.compile(r"[_\s]+")
_PHONE_NON_DIGIT_RE = re.compile(r"\D+")
_CURRENCY_PREFIX_RE = re.compile(r"^(?:₹|rs\.?|inr)\s*", re.IGNORECASE)
_PHONE_RE = re.compile(r"[6789]\d{9}")


def normalize_header(value: str) -> str:
    """Normalize a CSV header for schema matching."""
    return _HEADER_SEPARATOR_RE.sub(" ", value.strip().lower())


def normalize_phone(value: str) -> str:
    """Return an Indian mobile number in canonical +91XXXXXXXXXX form."""
    digits = _PHONE_NON_DIGIT_RE.sub("", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _PHONE_RE.fullmatch(digits):
        raise ValueError("invalid_phone")
    return f"+91{digits}"


def parse_date(value: str) -> date:
    """Parse one of the date formats allowed by the assignment."""
    value = value.strip()
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y")
    for format_string in formats:
        try:
            return datetime.strptime(value.title(), format_string).date()
        except ValueError:
            continue
    raise ValueError("invalid_date")


def parse_decimal(value: str) -> Decimal:
    """Parse a non-negative amount and round it to two decimal places."""
    cleaned = _CURRENCY_PREFIX_RE.sub("", value.strip()).replace(",", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError("invalid_decimal") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("invalid_decimal")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_enum(value: str, allowed_values: Iterable[str]) -> str:
    """Match an enum case-insensitively and return its lower-case value."""
    normalized = value.strip().lower()
    allowed = {item.strip().lower() for item in allowed_values}
    if normalized not in allowed:
        raise ValueError("invalid_enum")
    return normalized

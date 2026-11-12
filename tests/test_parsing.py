from datetime import date
from decimal import Decimal

import pytest

from solution.parsing import (
    normalize_header,
    normalize_phone,
    parse_date,
    parse_decimal,
    parse_enum,
)


def test_normalize_header_collapses_spaces_and_underscores():
    assert normalize_header("  Insured__Name\t") == "insured name"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("91-98765-43210", "+919876543210"),
        ("(+91) 98765 43210", "+919876543210"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["123456789", "5123456789", "N/A"])
def test_normalize_phone_rejects_invalid_values(raw):
    with pytest.raises(ValueError, match="invalid_phone"):
        normalize_phone(raw)


@pytest.mark.parametrize(
    "raw",
    ["2026-12-01", "01/12/2026", "01-12-2026", "01-dec-2026"],
)
def test_parse_date_accepts_specified_formats(raw):
    assert parse_date(raw) == date(2026, 12, 1)


def test_parse_date_rejects_impossible_date():
    with pytest.raises(ValueError, match="invalid_date"):
        parse_date("31/02/2026")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("₹12,500", Decimal("12500.00")),
        ("Rs. 12500", Decimal("12500.00")),
        ("INR 12500.505", Decimal("12500.51")),
    ],
)
def test_parse_decimal(raw, expected):
    assert parse_decimal(raw) == expected


def test_parse_decimal_rejects_negative_values():
    with pytest.raises(ValueError, match="invalid_decimal"):
        parse_decimal("-1")


def test_parse_enum_is_case_insensitive():
    assert parse_enum(" HI ", ["en", "hi"]) == "hi"


def test_parse_enum_rejects_unknown_value():
    with pytest.raises(ValueError, match="invalid_enum"):
        parse_enum("Hindi", ["en", "hi"])

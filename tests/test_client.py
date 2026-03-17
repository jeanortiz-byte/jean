"""Tests for the NetSuiteClient helper functions."""

import pytest
from src.client import _account_subdomain


@pytest.mark.parametrize(
    "account_id, expected",
    [
        ("1234567", "1234567"),
        ("1234567_SB1", "1234567-sb1"),
        ("ABCDEF_SB2", "abcdef-sb2"),
        ("myaccount", "myaccount"),
    ],
)
def test_account_subdomain(account_id: str, expected: str) -> None:
    assert _account_subdomain(account_id) == expected

"""Tests for downloader helpers."""

import pytest
from src.downloader import _safe_filename, _bill_filename


class TestSafeFilename:
    def test_strips_special_chars(self):
        assert _safe_filename("Acme/Corp & Co.") == "Acme_Corp_Co."

    def test_collapses_underscores(self):
        result = _safe_filename("a  b   c")
        assert "__" not in result

    def test_max_length(self):
        long = "a" * 200
        assert len(_safe_filename(long, max_len=80)) <= 80

    def test_unicode_normalisation(self):
        result = _safe_filename("Café Münster")
        assert "é" not in result
        assert "ü" not in result


class TestBillFilename:
    def test_standard_bill(self):
        bill = {
            "id": "999",
            "tranid": "BILL-001",
            "trandate": "2024-03-15",
            "vendor_name": "Acme Corp",
        }
        fname = _bill_filename(bill)
        assert fname.endswith(".pdf")
        assert "Acme_Corp" in fname
        assert "BILL-001" in fname
        assert "2024-03-15" in fname

    def test_missing_vendor_name_falls_back_to_vendor_id(self):
        bill = {"id": "1", "tranid": "X", "trandate": "2024-01-01", "vendor_id": "v42"}
        fname = _bill_filename(bill)
        assert "v42" in fname

    def test_all_missing(self):
        fname = _bill_filename({})
        assert fname.endswith(".pdf")

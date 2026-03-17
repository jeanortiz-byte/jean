"""
Invoice search and PDF download orchestration.

Provides high-level functions that combine querying for VendorBill records
and persisting their PDFs to disk.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterator

from tqdm import tqdm

from .client import NetSuiteClient

logger = logging.getLogger(__name__)

# SuiteQL query used to discover vendor bills.  Returns the minimum set of
# fields needed to name the output file and drive the PDF download.
_VENDOR_BILL_QUERY = """
SELECT
    t.id,
    t.tranid,
    t.trandate,
    t.duedate,
    t.foreigntotal  AS amount,
    t.foreigncurrency AS currency,
    e.entityid      AS vendor_id,
    e.altname       AS vendor_name,
    t.status
FROM
    transaction t
    LEFT JOIN entity e ON t.entity = e.id
WHERE
    t.type = 'VendBill'
ORDER BY
    t.trandate DESC, t.id DESC
"""

_VENDOR_BILL_QUERY_WITH_VENDOR = _VENDOR_BILL_QUERY.rstrip() + "\n"


def _safe_filename(value: str, max_len: int = 80) -> str:
    """Convert an arbitrary string into a safe file-system name."""
    # Normalize unicode → ASCII equivalents where possible
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", errors="ignore").decode()
    # Replace any character that isn't alphanumeric, dash, dot, or underscore
    value = re.sub(r"[^\w.\-]", "_", value)
    # Collapse runs of underscores/spaces
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:max_len]


def _bill_filename(bill: dict) -> str:
    """
    Build a descriptive, filesystem-safe filename for a vendor bill PDF.

    Format: ``{vendor_name}_{tran_id}_{date}.pdf``
    """
    vendor = _safe_filename(bill.get("vendor_name") or bill.get("vendor_id") or "unknown_vendor")
    tran_id = _safe_filename(str(bill.get("tranid") or bill.get("id") or "no_id"))
    date_raw = str(bill.get("trandate") or "")
    date = re.sub(r"[^\d\-]", "", date_raw)[:10] or "no_date"
    return f"{vendor}_{tran_id}_{date}.pdf"


def search_vendor_bills(
    client: NetSuiteClient,
    vendor_id: str | None = None,
    vendor_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
) -> Iterator[dict]:
    """
    Yield vendor bill rows matching the supplied filters.

    All filters are optional; omitting them returns every vendor bill.

    Parameters
    ----------
    client:       Authenticated NetSuiteClient instance.
    vendor_id:    NetSuite internal entity ID for the vendor.
    vendor_name:  Partial vendor name for LIKE-style filtering (applied
                  client-side after retrieval because SuiteQL LIKE support
                  varies by field type).
    start_date:   Inclusive lower bound on trandate (``YYYY-MM-DD``).
    end_date:     Inclusive upper bound on trandate (``YYYY-MM-DD``).
    status:       NetSuite bill status code, e.g. ``'open'``, ``'paid'``.
    """
    query = _VENDOR_BILL_QUERY

    # Build WHERE clause additions
    extra_conditions: list[str] = []
    if vendor_id:
        extra_conditions.append(f"t.entity = {int(vendor_id)}")
    if start_date:
        extra_conditions.append(f"t.trandate >= TO_DATE('{start_date}', 'YYYY-MM-DD')")
    if end_date:
        extra_conditions.append(f"t.trandate <= TO_DATE('{end_date}', 'YYYY-MM-DD')")
    if status:
        extra_conditions.append(f"LOWER(t.status) = LOWER('{status}')")

    if extra_conditions:
        query = query.replace(
            "WHERE\n    t.type = 'VendBill'",
            "WHERE\n    t.type = 'VendBill'\n    AND " + "\n    AND ".join(extra_conditions),
        )

    for row in client.iter_suiteql(query):
        # Client-side vendor name filter (case-insensitive substring match)
        if vendor_name:
            name = (row.get("vendor_name") or "").lower()
            if vendor_name.lower() not in name:
                continue
        yield row


def download_invoices(
    client: NetSuiteClient,
    output_dir: str | Path = "invoices",
    vendor_id: str | None = None,
    vendor_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    skip_existing: bool = True,
) -> list[Path]:
    """
    Search for vendor bills matching the given filters, download each as a
    PDF, and write it to ``output_dir``.

    Returns a list of paths to the files that were written.

    Parameters
    ----------
    client:        Authenticated NetSuiteClient.
    output_dir:    Directory where PDFs will be saved (created if absent).
    vendor_id:     Narrow to a single vendor by internal ID.
    vendor_name:   Narrow by vendor name substring.
    start_date:    Earliest trandate to include (``YYYY-MM-DD``).
    end_date:      Latest trandate to include (``YYYY-MM-DD``).
    status:        Filter by bill status (e.g. ``'open'``, ``'paid'``).
    skip_existing: When True, skip bills whose PDF already exists on disk.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("Searching for vendor bills…")
    bills = list(
        search_vendor_bills(
            client,
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            start_date=start_date,
            end_date=end_date,
            status=status,
        )
    )

    if not bills:
        logger.info("No vendor bills found matching the specified filters.")
        return []

    logger.info("Found %d vendor bill(s). Beginning PDF downloads…", len(bills))

    downloaded: list[Path] = []
    skipped = 0
    errors = 0

    for bill in tqdm(bills, desc="Downloading invoices", unit="invoice"):
        internal_id = bill.get("id")
        if not internal_id:
            logger.warning("Skipping bill with no internal ID: %s", bill)
            errors += 1
            continue

        filename = _bill_filename(bill)
        dest = output_path / filename

        if skip_existing and dest.exists():
            logger.debug("Skipping existing file: %s", dest)
            skipped += 1
            continue

        try:
            pdf_bytes = client.download_vendor_bill_pdf(internal_id)
        except Exception as exc:
            logger.error(
                "Failed to download PDF for bill ID %s (%s): %s",
                internal_id,
                bill.get("tranid"),
                exc,
            )
            errors += 1
            continue

        dest.write_bytes(pdf_bytes)
        downloaded.append(dest)
        logger.debug("Saved %s (%d bytes)", dest, len(pdf_bytes))

    logger.info(
        "Done. Downloaded: %d | Skipped: %d | Errors: %d",
        len(downloaded),
        skipped,
        errors,
    )
    return downloaded

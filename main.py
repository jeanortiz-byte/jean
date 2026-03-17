#!/usr/bin/env python3
"""
NetSuite Vendor Invoice Downloader
===================================
Download vendor bill PDFs from NetSuite via the REST API.

Usage examples
--------------
Download all vendor bills:
    python main.py download

Download bills for a specific vendor (by name substring):
    python main.py download --vendor-name "Acme"

Download bills for a specific vendor (by internal ID):
    python main.py download --vendor-id 123

Filter by date range:
    python main.py download --start-date 2024-01-01 --end-date 2024-12-31

Filter by status:
    python main.py download --status open

Combine filters:
    python main.py download --vendor-name "Acme" --start-date 2024-01-01

List vendors (without downloading):
    python main.py list-vendors

List vendor bills (without downloading):
    python main.py list-bills --vendor-name "Acme"
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env file before importing modules that read env vars
load_dotenv()

from src.client import NetSuiteClient
from src.downloader import download_invoices, search_vendor_bills

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _make_client() -> NetSuiteClient:
    """Instantiate a NetSuiteClient, surfacing credential errors clearly."""
    try:
        return NetSuiteClient()
    except EnvironmentError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        click.echo(
            "Copy .env.example to .env and fill in your NetSuite credentials.",
            err=True,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.version_option("1.0.0", prog_name="ns-invoices")
def cli() -> None:
    """NetSuite vendor invoice downloader."""


# ---------------------------------------------------------------------------
# download command
# ---------------------------------------------------------------------------

@cli.command("download")
@click.option("--vendor-id", default=None, help="Vendor internal ID (exact match).")
@click.option(
    "--vendor-name",
    default=None,
    help="Vendor name substring (case-insensitive).",
)
@click.option(
    "--start-date",
    default=None,
    metavar="YYYY-MM-DD",
    help="Earliest transaction date to include.",
)
@click.option(
    "--end-date",
    default=None,
    metavar="YYYY-MM-DD",
    help="Latest transaction date to include.",
)
@click.option(
    "--status",
    default=None,
    type=click.Choice(["open", "paid", "pendingApproval", "rejected"], case_sensitive=False),
    help="Filter by bill status.",
)
@click.option(
    "--output-dir",
    default=None,
    help="Directory to save PDFs (default: $NS_OUTPUT_DIR or ./invoices).",
)
@click.option(
    "--no-skip",
    is_flag=True,
    default=False,
    help="Re-download files that already exist on disk.",
)
def download_cmd(
    vendor_id: str | None,
    vendor_name: str | None,
    start_date: str | None,
    end_date: str | None,
    status: str | None,
    output_dir: str | None,
    no_skip: bool,
) -> None:
    """Download vendor bill PDFs from NetSuite."""
    client = _make_client()

    resolved_output = output_dir or os.environ.get("NS_OUTPUT_DIR", "invoices")

    downloaded = download_invoices(
        client=client,
        output_dir=resolved_output,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        start_date=start_date,
        end_date=end_date,
        status=status,
        skip_existing=not no_skip,
    )

    if downloaded:
        click.echo(f"\nSaved {len(downloaded)} invoice(s) to: {Path(resolved_output).resolve()}")
    else:
        click.echo("No new invoices were downloaded.")


# ---------------------------------------------------------------------------
# list-bills command
# ---------------------------------------------------------------------------

@cli.command("list-bills")
@click.option("--vendor-id", default=None, help="Vendor internal ID (exact match).")
@click.option("--vendor-name", default=None, help="Vendor name substring.")
@click.option("--start-date", default=None, metavar="YYYY-MM-DD")
@click.option("--end-date", default=None, metavar="YYYY-MM-DD")
@click.option("--status", default=None, help="Bill status filter.")
@click.option(
    "--limit",
    default=50,
    show_default=True,
    help="Max rows to display.",
)
def list_bills_cmd(
    vendor_id: str | None,
    vendor_name: str | None,
    start_date: str | None,
    end_date: str | None,
    status: str | None,
    limit: int,
) -> None:
    """List vendor bills without downloading them."""
    client = _make_client()

    bills = []
    for bill in search_vendor_bills(
        client,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        start_date=start_date,
        end_date=end_date,
        status=status,
    ):
        bills.append(bill)
        if len(bills) >= limit:
            break

    if not bills:
        click.echo("No vendor bills found.")
        return

    # Pretty-print a simple table
    header = f"{'ID':<10} {'Tran ID':<20} {'Date':<12} {'Vendor':<35} {'Amount':<15} {'Status'}"
    click.echo(header)
    click.echo("-" * len(header))
    for b in bills:
        amount = b.get("amount") or ""
        currency = b.get("currency") or ""
        amount_str = f"{amount} {currency}".strip()
        click.echo(
            f"{str(b.get('id','')):<10} "
            f"{str(b.get('tranid','')):<20} "
            f"{str(b.get('trandate','')):<12} "
            f"{str(b.get('vendor_name') or b.get('vendor_id','')):<35} "
            f"{amount_str:<15} "
            f"{b.get('status','')}"
        )


# ---------------------------------------------------------------------------
# list-vendors command
# ---------------------------------------------------------------------------

@cli.command("list-vendors")
@click.option(
    "--limit",
    default=50,
    show_default=True,
    help="Max rows to display.",
)
def list_vendors_cmd(limit: int) -> None:
    """List vendors that have vendor bills in NetSuite."""
    client = _make_client()

    query = """
SELECT DISTINCT
    e.id,
    e.entityid,
    e.altname AS vendor_name,
    e.email
FROM
    transaction t
    JOIN entity e ON t.entity = e.id
WHERE
    t.type = 'VendBill'
ORDER BY
    e.altname ASC
"""
    vendors = []
    for row in client.iter_suiteql(query):
        vendors.append(row)
        if len(vendors) >= limit:
            break

    if not vendors:
        click.echo("No vendors with bills found.")
        return

    header = f"{'Internal ID':<15} {'Entity ID':<25} {'Name':<40} {'Email'}"
    click.echo(header)
    click.echo("-" * len(header))
    for v in vendors:
        click.echo(
            f"{str(v.get('id','')):<15} "
            f"{str(v.get('entityid','')):<25} "
            f"{str(v.get('vendor_name','')):<40} "
            f"{v.get('email','')}"
        )


if __name__ == "__main__":
    cli()

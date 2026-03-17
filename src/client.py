"""
NetSuite REST API client.

Wraps the two key NetSuite API surfaces used by this tool:
  1. SuiteTalk REST Record API  – list / read VendorBill records
  2. SuiteQL REST API           – flexible SQL-like querying
  3. Transaction print endpoint – download PDFs
"""

from __future__ import annotations

import os
import re
import time
import logging
from typing import Any, Iterator
from urllib.parse import urlencode

import requests
from requests import Response

from .auth import build_oauth

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BACKOFF_BASE = 2  # seconds


def _account_subdomain(account_id: str) -> str:
    """Convert account ID to the subdomain used in NetSuite API URLs.

    NetSuite replaces underscores with hyphens and lowercases the ID.
    E.g. '1234567_SB1' → '1234567-sb1'
    """
    return account_id.replace("_", "-").lower()


class NetSuiteClient:
    """Thin HTTP client for the NetSuite REST APIs."""

    def __init__(
        self,
        account_id: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        token_id: str | None = None,
        token_secret: str | None = None,
    ) -> None:
        self.account_id = (account_id or os.environ.get("NS_ACCOUNT_ID", "")).strip()
        if not self.account_id:
            raise EnvironmentError("NS_ACCOUNT_ID must be set.")

        subdomain = _account_subdomain(self.account_id)

        self._record_base = (
            f"https://{subdomain}.suitetalk.api.netsuite.com"
            "/services/rest/record/v1"
        )
        self._query_base = (
            f"https://{subdomain}.suitetalk.api.netsuite.com"
            "/services/rest/query/v1"
        )
        self._app_base = f"https://{subdomain}.app.netsuite.com"

        self._oauth = build_oauth(
            account_id=self.account_id,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            token_id=token_id,
            token_secret=token_secret,
        )
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: Any = None,
        headers: dict | None = None,
        stream: bool = False,
    ) -> Response:
        """Send an authenticated request with automatic retries."""
        base_headers = {"Content-Type": "application/json"}
        if headers:
            base_headers.update(headers)

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=base_headers,
                    auth=self._oauth,
                    stream=stream,
                    timeout=60,
                )
            except requests.RequestException as exc:
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning("Request error (%s); retrying in %ss…", exc, wait)
                    time.sleep(wait)
                    continue
                raise

            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "HTTP %s from %s; retrying in %ss…", resp.status_code, url, wait
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp

        raise RuntimeError(f"Exhausted retries for {url}")

    # ------------------------------------------------------------------
    # Record API helpers
    # ------------------------------------------------------------------

    def get_vendor_bill(self, internal_id: str | int) -> dict:
        """Fetch a single VendorBill record by its internal ID."""
        url = f"{self._record_base}/vendorbill/{internal_id}"
        return self._request("GET", url).json()

    def list_vendor_bills(
        self,
        limit: int = 100,
        offset: int = 0,
        fields: list[str] | None = None,
    ) -> dict:
        """
        Return one page of VendorBill records.

        ``fields`` narrows the response to specific field names, reducing
        payload size.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = ",".join(fields)
        url = f"{self._record_base}/vendorbill"
        return self._request("GET", url, params=params).json()

    def iter_vendor_bills(
        self,
        fields: list[str] | None = None,
        page_size: int = 100,
    ) -> Iterator[dict]:
        """
        Yield every VendorBill record, transparently paginating through
        the full result set.
        """
        offset = 0
        while True:
            page = self.list_vendor_bills(
                limit=page_size, offset=offset, fields=fields
            )
            items = page.get("items", [])
            yield from items
            if not page.get("hasMore", False):
                break
            offset += page_size

    # ------------------------------------------------------------------
    # SuiteQL helpers
    # ------------------------------------------------------------------

    def suiteql(
        self,
        query: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """Execute a SuiteQL query and return the raw response dict."""
        url = f"{self._query_base}/suiteql"
        params = {"limit": limit, "offset": offset}
        return self._request("POST", url, params=params, json={"q": query}).json()

    def iter_suiteql(self, query: str, page_size: int = 1000) -> Iterator[dict]:
        """Yield every row from a SuiteQL query, paginating automatically."""
        offset = 0
        while True:
            page = self.suiteql(query, limit=page_size, offset=offset)
            items = page.get("items", [])
            yield from items
            if not page.get("hasMore", False):
                break
            offset += page_size

    # ------------------------------------------------------------------
    # PDF download
    # ------------------------------------------------------------------

    def download_vendor_bill_pdf(self, internal_id: str | int) -> bytes:
        """
        Download the PDF for a VendorBill and return the raw bytes.

        NetSuite generates transaction PDFs through its application print
        endpoint, authenticated with the same OAuth 1.0 TBA credentials.
        """
        url = f"{self._app_base}/app/accounting/print/NLPopupPrint.nl"
        params = {
            "regular": "T",
            "setlang": "T",
            "forceLanguage": "en_US",
            "trantype": "vendorbill",
            "id": str(internal_id),
        }
        resp = self._request(
            "GET",
            url,
            params=params,
            headers={"Accept": "application/pdf"},
            stream=True,
        )
        return resp.content

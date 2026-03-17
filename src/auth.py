"""
NetSuite OAuth 1.0 Token-Based Authentication (TBA).

NetSuite requires the account ID as the OAuth realm, HMAC-SHA256 as the
signature method, and specific header formatting. This module wraps
requests-oauthlib to meet those requirements.
"""

import os
from requests_oauthlib import OAuth1


def _normalize_account_id(account_id: str) -> str:
    """
    NetSuite uses hyphens in subdomain names but underscores in the account ID
    field. E.g. '1234567_SB1' → '1234567-SB1' for URL construction, but the
    raw value is used as the OAuth realm.
    """
    return account_id.strip()


def build_oauth(
    account_id: str | None = None,
    consumer_key: str | None = None,
    consumer_secret: str | None = None,
    token_id: str | None = None,
    token_secret: str | None = None,
) -> OAuth1:
    """
    Return a configured OAuth1 object ready to be passed as the ``auth``
    parameter to any ``requests`` call.

    Values default to the corresponding environment variables when not supplied
    explicitly:
      - NS_ACCOUNT_ID
      - NS_CONSUMER_KEY
      - NS_CONSUMER_SECRET
      - NS_TOKEN_ID
      - NS_TOKEN_SECRET
    """
    account_id = account_id or os.environ.get("NS_ACCOUNT_ID", "")
    consumer_key = consumer_key or os.environ.get("NS_CONSUMER_KEY", "")
    consumer_secret = consumer_secret or os.environ.get("NS_CONSUMER_SECRET", "")
    token_id = token_id or os.environ.get("NS_TOKEN_ID", "")
    token_secret = token_secret or os.environ.get("NS_TOKEN_SECRET", "")

    missing = [
        name
        for name, val in [
            ("NS_ACCOUNT_ID", account_id),
            ("NS_CONSUMER_KEY", consumer_key),
            ("NS_CONSUMER_SECRET", consumer_secret),
            ("NS_TOKEN_ID", token_id),
            ("NS_TOKEN_SECRET", token_secret),
        ]
        if not val
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required NetSuite credentials: {', '.join(missing)}. "
            "Set them in your .env file or as environment variables."
        )

    return OAuth1(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token_id,
        resource_owner_secret=token_secret,
        signature_method="HMAC-SHA256",
        realm=_normalize_account_id(account_id),
    )

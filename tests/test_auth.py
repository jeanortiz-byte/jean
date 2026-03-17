"""Tests for the auth module."""

import pytest
from unittest.mock import patch


def test_build_oauth_missing_credentials():
    """build_oauth raises EnvironmentError when credentials are absent."""
    from src.auth import build_oauth

    with patch.dict("os.environ", {}, clear=True):
        # Remove all NS_ env vars
        import os
        for key in list(os.environ.keys()):
            if key.startswith("NS_"):
                del os.environ[key]

        with pytest.raises(EnvironmentError, match="Missing required"):
            build_oauth()


def test_build_oauth_with_all_credentials():
    """build_oauth returns an OAuth1 object when all credentials are present."""
    from src.auth import build_oauth
    from requests_oauthlib import OAuth1

    env = {
        "NS_ACCOUNT_ID": "1234567",
        "NS_CONSUMER_KEY": "ck",
        "NS_CONSUMER_SECRET": "cs",
        "NS_TOKEN_ID": "ti",
        "NS_TOKEN_SECRET": "ts",
    }
    with patch.dict("os.environ", env, clear=False):
        auth = build_oauth()
    assert isinstance(auth, OAuth1)

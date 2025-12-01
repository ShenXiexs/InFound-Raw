"""Helpers for retrieving sanitized credential placeholders."""
from __future__ import annotations

import os
from typing import Dict


class MissingDefaultAccountError(RuntimeError):
    """Raised when no fallback account details are available."""


def get_default_account_from_env() -> Dict[str, str]:
    """Return the default account profile sourced from environment variables."""

    login_email = os.getenv("DEFAULT_TTSHOP_EMAIL", "").strip()
    login_password = os.getenv("DEFAULT_TTSHOP_PASSWORD", "").strip()
    gmail_username = os.getenv("DEFAULT_GMAIL_USERNAME", login_email).strip()
    gmail_app_password = os.getenv("DEFAULT_GMAIL_APP_PASSWORD", "").strip()

    if not all([login_email, login_password, gmail_username, gmail_app_password]):
        raise MissingDefaultAccountError(
            "Set DEFAULT_TTSHOP_EMAIL/DEFAULT_TTSHOP_PASSWORD/"
            "DEFAULT_GMAIL_USERNAME/DEFAULT_GMAIL_APP_PASSWORD or pass account_info explicitly."
        )

    return {
        "login_email": login_email,
        "login_password": login_password,
        "gmail_username": gmail_username,
        "gmail_app_password": gmail_app_password,
        "name": os.getenv("DEFAULT_ACCOUNT_NAME", "Default Account"),
        "id": -1,
    }


__all__ = ["get_default_account_from_env", "MissingDefaultAccountError"]

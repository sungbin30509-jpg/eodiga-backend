"""Project configuration.

Loads environment variables from the project-root ``.env`` file and exposes
project paths and safe accessors for API credentials.

Security rules enforced here:
- API key values are never printed, logged, or embedded in exception messages.
- Only the *name* of a missing variable is reported.
- This module performs no network calls.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
ENV_FILE: Path = PROJECT_ROOT / ".env"

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
MASTER_DIR: Path = DATA_DIR / "master"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# Load .env once at import time. Existing OS environment variables take
# precedence over values in the file (override=False).
load_dotenv(ENV_FILE, override=False)

# ---------------------------------------------------------------------------
# Environment variable names (names only, never values)
# ---------------------------------------------------------------------------

GITS_API_KEY_NAME = "GITS_API_KEY"
ITS_API_KEY_NAME = "ITS_API_KEY"
KMA_API_KEY_NAME = "KMA_API_KEY"  # legacy single-key name (fallback only)
KMA_ASOS_API_KEY_NAME = "KMA_ASOS_API_KEY"  # data.go.kr ServiceKey approved for AsosHourlyInfoService
KMA_FORECAST_API_KEY_NAME = "KMA_FORECAST_API_KEY"  # data.go.kr ServiceKey for VilageFcstInfoService_2.0

API_KEY_NAMES: tuple[str, ...] = (
    GITS_API_KEY_NAME,
    ITS_API_KEY_NAME,
    KMA_API_KEY_NAME,
    KMA_ASOS_API_KEY_NAME,
    KMA_FORECAST_API_KEY_NAME,
)


class MissingApiKeyError(RuntimeError):
    """Raised when a required API key is not set.

    The message contains only the variable name, never its value.
    """


def get_api_key(name: str, *, required: bool = False) -> str | None:
    """Return the API key stored in environment variable ``name``.

    Args:
        name: Environment variable name, e.g. ``"GITS_API_KEY"``.
        required: If True, raise ``MissingApiKeyError`` when the key is empty.

    Returns:
        The key value, or ``None`` if it is not set and ``required`` is False.

    Callers must not print or log the returned value.
    """
    value = os.getenv(name, "").strip()
    if value:
        return value
    if required:
        raise MissingApiKeyError(f"Environment variable {name} is not set")
    return None


def get_kma_asos_key(*, required: bool = True) -> str | None:
    """Return the data.go.kr key for the ASOS hourly service (KMA_ASOS_API_KEY, else legacy KMA_API_KEY)."""
    value = get_api_key(KMA_ASOS_API_KEY_NAME) or get_api_key(KMA_API_KEY_NAME)
    if value is None and required:
        raise MissingApiKeyError(f"Neither {KMA_ASOS_API_KEY_NAME} nor {KMA_API_KEY_NAME} is set")
    return value


def has_api_key(name: str) -> bool:
    """Return True if environment variable ``name`` holds a non-empty value."""
    return get_api_key(name) is not None


def api_key_status() -> dict[str, bool]:
    """Return ``{variable_name: is_set}`` for every known API key.

    Safe to print: contains only names and booleans.
    """
    return {name: has_api_key(name) for name in API_KEY_NAMES}


__all__ = [
    "PROJECT_ROOT",
    "ENV_FILE",
    "DATA_DIR",
    "RAW_DIR",
    "PROCESSED_DIR",
    "MASTER_DIR",
    "LOGS_DIR",
    "GITS_API_KEY_NAME",
    "ITS_API_KEY_NAME",
    "KMA_API_KEY_NAME",
    "KMA_ASOS_API_KEY_NAME",
    "KMA_FORECAST_API_KEY_NAME",
    "API_KEY_NAMES",
    "get_kma_asos_key",
    "MissingApiKeyError",
    "get_api_key",
    "has_api_key",
    "api_key_status",
]

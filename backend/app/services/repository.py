"""Supabase persistence layer for price reconciliation history.

Persists spot-reconciliation snapshots to the `price_history` Supabase
table and queries historical data ordered by timestamp descending for
the dashboard deviation chart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from app.core.config import settings


class RepositoryNotConfiguredError(Exception):
    """Raised when SUPABASE_URL or SUPABASE_KEY is missing."""


_client: Client | None = None


def get_supabase_client() -> Client:
    """Returns a cached or newly initialized Supabase client instance.

    Raises:
        RepositoryNotConfiguredError: If SUPABASE_URL or SUPABASE_KEY is not configured.
    """
    global _client
    if _client is not None:
        return _client

    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise RepositoryNotConfiguredError(
            "SUPABASE_URL and SUPABASE_KEY must be configured on this server"
        )

    _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client


def set_supabase_client(client: Client | None) -> None:
    """Sets or clears the cached Supabase client (primarily for testing)."""
    global _client
    _client = client


def record_price(
    on_chain_price_usd: float,
    spot_price_usd: float,
    deviation_bps: float,
    trading_session: str,
    recorded_at: datetime | str | None = None,
    client: Client | None = None,
) -> dict[str, Any]:
    """Persists a reconciliation snapshot into the price_history table.

    :param on_chain_price_usd: Aggregated on-chain XAU/USD price.
    :param spot_price_usd: Spot reference XAU/USD price.
    :param deviation_bps: Absolute deviation in basis points.
    :param trading_session: Active trading session name (asia/london/new_york/off_hours).
    :param recorded_at: Optional timestamp; defaults to current UTC time.
    :param client: Optional Supabase client instance (for testing).
    :return: The inserted row data dictionary.
    """
    client = client or get_supabase_client()

    if recorded_at is None:
        recorded_at_str = datetime.now(timezone.utc).isoformat()
    elif isinstance(recorded_at, datetime):
        recorded_at_str = recorded_at.isoformat()
    else:
        recorded_at_str = str(recorded_at)

    payload = {
        "on_chain_price_usd": float(on_chain_price_usd),
        "spot_price_usd": float(spot_price_usd),
        "deviation_bps": float(deviation_bps),
        "trading_session": str(trading_session),
        "recorded_at": recorded_at_str,
    }

    result = client.table("price_history").insert(payload).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    return payload


def get_price_history(
    limit: int = 100,
    client: Client | None = None,
) -> list[dict[str, Any]]:
    """Returns historical price reconciliation snapshots ordered chronologically descending.

    :param limit: Maximum number of rows to retrieve (default 100).
    :param client: Optional Supabase client instance (for testing).
    :return: List of row dictionaries.
    """
    client = client or get_supabase_client()

    result = (
        client.table("price_history")
        .select("*")
        .order("recorded_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# Alias matching acceptance criteria naming
get_history = get_price_history


class PriceRepository:
    """Object-oriented repository wrapper for price history operations."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        if self._client is not None:
            return self._client
        return get_supabase_client()

    def record_price(
        self,
        on_chain_price_usd: float,
        spot_price_usd: float,
        deviation_bps: float,
        trading_session: str,
        recorded_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        return record_price(
            on_chain_price_usd=on_chain_price_usd,
            spot_price_usd=spot_price_usd,
            deviation_bps=deviation_bps,
            trading_session=trading_session,
            recorded_at=recorded_at,
            client=self.client,
        )

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return get_price_history(limit=limit, client=self.client)

"""Tests for Supabase price history repository and pricing routes.

CI runs without live Supabase credentials; all Supabase client calls
are tested either with a mocked client or verified to raise
RepositoryNotConfiguredError when unconfigured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import repository as repo_module
from app.services.repository import (
    PriceRepository,
    RepositoryNotConfiguredError,
    get_price_history,
    record_price,
    set_supabase_client,
)


class _FakeQueryResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(self, initial_data: list[dict[str, Any]] | None = None) -> None:
        self.initial_data = initial_data or []
        self.inserted_rows: list[dict[str, Any]] = []
        self.selected_columns: tuple[Any, ...] = ()
        self.order_call: tuple[str, bool] | None = None
        self.limit_val: int | None = None

    def insert(
        self, payload: dict[str, Any] | list[dict[str, Any]]
    ) -> _FakeQueryBuilder:
        if isinstance(payload, dict):
            self.inserted_rows.append(payload)
        else:
            self.inserted_rows.extend(payload)
        return self

    def select(self, *columns: Any) -> _FakeQueryBuilder:
        self.selected_columns = columns
        return self

    def order(self, column: str, desc: bool = False) -> _FakeQueryBuilder:
        self.order_call = (column, desc)
        return self

    def limit(self, count: int) -> _FakeQueryBuilder:
        self.limit_val = count
        return self

    def execute(self) -> _FakeQueryResult:
        if self.inserted_rows:
            return _FakeQueryResult(data=list(self.inserted_rows))
        data = list(self.initial_data)
        if self.limit_val is not None:
            data = data[: self.limit_val]
        return _FakeQueryResult(data=data)


class _FakeSupabaseClient:
    def __init__(self, initial_rows: list[dict[str, Any]] | None = None) -> None:
        self.query_builder = _FakeQueryBuilder(initial_rows)

    def table(self, table_name: str) -> _FakeQueryBuilder:
        assert table_name == "price_history"
        return self.query_builder


@pytest.fixture(autouse=True)
def _reset_repo_client():
    """Ensure cached client is cleared before and after each test."""
    set_supabase_client(None)
    yield
    set_supabase_client(None)


def test_record_price_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "")

    with pytest.raises(RepositoryNotConfiguredError) as exc_info:
        record_price(
            on_chain_price_usd=2000.0,
            spot_price_usd=1995.0,
            deviation_bps=25.06,
            trading_session="london",
        )
    assert "SUPABASE_URL and SUPABASE_KEY must be configured" in str(exc_info.value)


def test_record_price_persists_row():
    fake_client = _FakeSupabaseClient()
    fixed_time = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)

    result = record_price(
        on_chain_price_usd=2050.0,
        spot_price_usd=2000.0,
        deviation_bps=250.0,
        trading_session="new_york",
        recorded_at=fixed_time,
        client=fake_client,
    )

    assert result["on_chain_price_usd"] == 2050.0
    assert result["spot_price_usd"] == 2000.0
    assert result["deviation_bps"] == 250.0
    assert result["trading_session"] == "new_york"
    assert result["recorded_at"] == fixed_time.isoformat()

    assert len(fake_client.query_builder.inserted_rows) == 1
    inserted = fake_client.query_builder.inserted_rows[0]
    assert inserted["deviation_bps"] == 250.0
    assert inserted["trading_session"] == "new_york"


def test_get_price_history_orders_descending():
    sample_rows = [
        {
            "id": 1,
            "on_chain_price_usd": 2010.0,
            "spot_price_usd": 2000.0,
            "deviation_bps": 50.0,
            "trading_session": "london",
            "recorded_at": "2026-10-04T12:00:00Z",
        },
        {
            "id": 2,
            "on_chain_price_usd": 2005.0,
            "spot_price_usd": 2000.0,
            "deviation_bps": 25.0,
            "trading_session": "asia",
            "recorded_at": "2026-10-04T11:00:00Z",
        },
    ]
    fake_client = _FakeSupabaseClient(initial_rows=sample_rows)

    rows = get_price_history(limit=50, client=fake_client)

    assert len(rows) == 2
    assert fake_client.query_builder.order_call == ("recorded_at", True)
    assert fake_client.query_builder.limit_val == 50
    assert rows[0]["id"] == 1


def test_price_repository_class_interface():
    fake_client = _FakeSupabaseClient()
    repo = PriceRepository(client=fake_client)

    recorded = repo.record_price(
        on_chain_price_usd=2000.0,
        spot_price_usd=2000.0,
        deviation_bps=0.0,
        trading_session="off_hours",
    )
    assert recorded["trading_session"] == "off_hours"
    assert len(fake_client.query_builder.inserted_rows) == 1

    history = repo.get_history(limit=10)
    assert isinstance(history, list)


def test_reconcile_endpoint_inserts_row(monkeypatch):
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(repo_module, "get_supabase_client", lambda: fake_client)

    client = TestClient(app)
    response = client.post(
        "/pricing/reconcile",
        json={"on_chain_price_usd": 2050.0, "spot_price_usd": 2000.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["on_chain_price_usd"] == 2050.0
    assert data["spot_price_usd"] == 2000.0
    assert data["deviation_bps"] == 250.0
    assert data["deviation_exceeds_threshold"] is True

    # Check persistence was triggered
    assert len(fake_client.query_builder.inserted_rows) == 1
    inserted = fake_client.query_builder.inserted_rows[0]
    assert inserted["on_chain_price_usd"] == 2050.0
    assert inserted["spot_price_usd"] == 2000.0
    assert inserted["deviation_bps"] == 250.0


def test_reconcile_endpoint_503_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "")

    client = TestClient(app)
    response = client.post(
        "/pricing/reconcile",
        json={"on_chain_price_usd": 2000.0, "spot_price_usd": 2000.0},
    )

    assert response.status_code == 503
    assert (
        "SUPABASE_URL and SUPABASE_KEY must be configured" in response.json()["detail"]
    )


def test_get_history_endpoint_returns_descending_rows(monkeypatch):
    sample_records = [
        {
            "id": 10,
            "on_chain_price_usd": 2020.0,
            "spot_price_usd": 2000.0,
            "deviation_bps": 100.0,
            "trading_session": "new_york",
            "recorded_at": "2026-10-04T14:00:00Z",
        },
        {
            "id": 9,
            "on_chain_price_usd": 2010.0,
            "spot_price_usd": 2000.0,
            "deviation_bps": 50.0,
            "trading_session": "london",
            "recorded_at": "2026-10-04T13:00:00Z",
        },
    ]
    fake_client = _FakeSupabaseClient(initial_rows=sample_records)
    monkeypatch.setattr(repo_module, "get_supabase_client", lambda: fake_client)

    client = TestClient(app)
    response = client.get("/pricing/history?limit=100")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["id"] == 10
    assert items[0]["deviation_bps"] == 100.0
    assert items[1]["id"] == 9
    assert items[1]["deviation_bps"] == 50.0


def test_get_history_endpoint_503_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "")

    client = TestClient(app)
    response = client.get("/pricing/history")

    assert response.status_code == 503
    assert (
        "SUPABASE_URL and SUPABASE_KEY must be configured" in response.json()["detail"]
    )

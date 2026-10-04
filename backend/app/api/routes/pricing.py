"""Routes for price aggregation and spot reconciliation."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.models.pricing import (
    AggregatedPrice,
    PriceHistoryRecord,
    PriceQuote,
    ReconciliationReport,
)
from app.services.oracle import aggregate_median, reconcile_with_spot
from app.services.repository import (
    RepositoryNotConfiguredError,
    get_price_history,
    record_price,
)

router = APIRouter()


class AggregateRequest(BaseModel):
    quotes: list[PriceQuote]


@router.post("/aggregate", response_model=AggregatedPrice)
async def aggregate_price(payload: AggregateRequest) -> AggregatedPrice:
    if not payload.quotes:
        raise HTTPException(status_code=400, detail="At least one quote is required")
    return aggregate_median(payload.quotes)


class ReconcileRequest(BaseModel):
    on_chain_price_usd: float
    spot_price_usd: float


@router.post("/reconcile", response_model=ReconciliationReport)
async def reconcile_price(payload: ReconcileRequest) -> ReconciliationReport:
    try:
        report = reconcile_with_spot(
            on_chain_price_usd=payload.on_chain_price_usd,
            spot_price_usd=payload.spot_price_usd,
            deviation_alert_threshold_bps=settings.DEVIATION_ALERT_THRESHOLD_BPS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        session_name = (
            report.trading_session.value
            if hasattr(report.trading_session, "value")
            else str(report.trading_session)
        )
        record_price(
            on_chain_price_usd=report.on_chain_price_usd,
            spot_price_usd=report.spot_price_usd,
            deviation_bps=report.deviation_bps,
            trading_session=session_name,
            recorded_at=report.checked_at,
        )
    except RepositoryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return report


@router.get("/history", response_model=list[PriceHistoryRecord])
async def get_history(limit: int = 100) -> list[PriceHistoryRecord]:
    try:
        rows = get_price_history(limit=limit)
        return [
            PriceHistoryRecord(**row) if isinstance(row, dict) else row for row in rows
        ]
    except RepositoryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

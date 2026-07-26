"""Models for the fee-sponsoring relayer (see app/services/relayer.py)."""

from pydantic import BaseModel


class SubmitTransactionRequest(BaseModel):
    xdr: str


class RelayerResult(BaseModel):
    success: bool
    hash: str | None = None
    error: str | None = None

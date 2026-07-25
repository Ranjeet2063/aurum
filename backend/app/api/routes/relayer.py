"""Route for fee-sponsored submission of passkey smart-wallet transactions.

See app/services/relayer.py for why this exists instead of passkey-kit's
built-in OpenZeppelin relayer path.
"""

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.models.relayer import RelayerResult, SubmitTransactionRequest
from app.services.relayer import RelayerNotConfiguredError, submit_signed_transaction

router = APIRouter()


def get_relayer_submit():
    return submit_signed_transaction


@router.post("/submit", response_model=RelayerResult)
async def submit(
    payload: SubmitTransactionRequest,
    submit_fn=Depends(get_relayer_submit),
) -> RelayerResult:
    # submit_fn blocks (network calls + polling sleeps) for up to
    # ~poll_timeout_seconds — run it off the event loop so a single slow
    # submission doesn't stall every other request this server is handling.
    try:
        return await run_in_threadpool(submit_fn, payload.xdr)
    except RelayerNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

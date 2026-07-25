"""Fee-sponsoring relayer for passkey smart-wallet transactions.

A passkey-kit smart wallet holds no XLM, so it can't pay its own
transaction fees. Rather than depend on passkey-kit's built-in relayer
path (a paid third-party service, OpenZeppelin Relayer Channels — see
docs/superpowers/specs/2026-07-25-passkey-secp256r1-signing-design.md),
this wraps an already-signed inner transaction in a fee-bump transaction
paid by a backend-held funded testnet keypair (`Settings.RELAYER_SECRET_KEY`)
and submits it via `SorobanServer`.

Freighter-signed transactions never go through this path — a classic
account pays its own fees directly (see frontend/lib/contract.ts).
"""

from __future__ import annotations

import time

from stellar_sdk import Keypair, SorobanServer, TransactionBuilder, TransactionEnvelope
from stellar_sdk import exceptions as stellar_exceptions

from app.core.config import settings
from app.models.relayer import RelayerResult

DEFAULT_BASE_FEE = 100_000  # stroops; generous headroom over the network minimum
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_POLL_TIMEOUT_SECONDS = 30.0


class RelayerNotConfiguredError(Exception):
    """Raised when RELAYER_SECRET_KEY isn't set. Callers (see
    app/api/routes/relayer.py) turn this into a 503 rather than silently
    accepting a request that can never actually submit."""


def submit_signed_transaction(
    xdr: str,
    *,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    poll_timeout_seconds: float = DEFAULT_POLL_TIMEOUT_SECONDS,
) -> RelayerResult:
    if not settings.RELAYER_SECRET_KEY:
        raise RelayerNotConfiguredError(
            "RELAYER_SECRET_KEY is not configured on this server"
        )

    fee_source = Keypair.from_secret(settings.RELAYER_SECRET_KEY)

    try:
        inner_envelope = TransactionEnvelope.from_xdr(
            xdr, settings.SOROBAN_NETWORK_PASSPHRASE
        )
        fee_bump = TransactionBuilder.build_fee_bump_transaction(
            fee_source=fee_source,
            base_fee=DEFAULT_BASE_FEE,
            inner_transaction_envelope=inner_envelope,
            network_passphrase=settings.SOROBAN_NETWORK_PASSPHRASE,
        )
        fee_bump.sign(fee_source)

        with SorobanServer(settings.SOROBAN_RPC_URL) as server:
            send_result = server.send_transaction(fee_bump)

            if send_result.status == "ERROR":
                return RelayerResult(
                    success=False,
                    error=f"Transaction rejected: {send_result.status}",
                )

            deadline = time.monotonic() + poll_timeout_seconds
            tx_hash = send_result.hash
            while time.monotonic() < deadline:
                get_result = server.get_transaction(tx_hash)
                if get_result.status == "SUCCESS":
                    return RelayerResult(success=True, hash=tx_hash)
                if get_result.status == "FAILED":
                    return RelayerResult(
                        success=False,
                        hash=tx_hash,
                        error="Transaction failed on-chain",
                    )
                time.sleep(poll_interval_seconds)

            return RelayerResult(
                success=False,
                hash=tx_hash,
                error="Timed out waiting for transaction confirmation",
            )
    except stellar_exceptions.SdkError as exc:
        return RelayerResult(success=False, error=str(exc))

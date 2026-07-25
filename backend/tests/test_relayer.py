"""Tests for the fee-sponsoring relayer service.

`stellar_sdk`'s real classes (Keypair, TransactionEnvelope,
TransactionBuilder, SorobanServer) are monkeypatched at the module
boundary rather than exercised directly — building a real signed XDR
envelope isn't needed to test this service's control flow (fee-bump,
submit, poll, map to RelayerResult), and doing so would require a live
network round-trip this test suite otherwise avoids.
"""

import pytest

from app.core.config import settings
from app.services import relayer as relayer_module
from app.services.relayer import RelayerNotConfiguredError, submit_signed_transaction


class _FakeKeypair:
    @staticmethod
    def from_secret(secret: str):
        return _FakeKeypair()


class _FakeFeeBump:
    def __init__(self):
        self.signed = False

    def sign(self, keypair):
        self.signed = True


class _FakeTransactionEnvelope:
    @staticmethod
    def from_xdr(xdr: str, network_passphrase: str):
        return f"envelope-for:{xdr}"


class _FakeTransactionBuilder:
    @staticmethod
    def build_fee_bump_transaction(
        fee_source, base_fee, inner_transaction_envelope, network_passphrase
    ):
        return _FakeFeeBump()


class _SendResult:
    def __init__(self, status: str, hash_: str = "fakehash"):
        self.status = status
        self.hash = hash_


class _GetResult:
    def __init__(self, status: str):
        self.status = status


class _FakeSorobanServer:
    def __init__(self, send_status="PENDING", get_statuses=("SUCCESS",)):
        self._send_status = send_status
        self._get_statuses = list(get_statuses)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def send_transaction(self, envelope):
        return _SendResult(self._send_status)

    def get_transaction(self, tx_hash):
        status = self._get_statuses.pop(0) if self._get_statuses else "NOT_FOUND"
        return _GetResult(status)


@pytest.fixture(autouse=True)
def _patch_stellar_sdk(monkeypatch):
    monkeypatch.setattr(relayer_module, "Keypair", _FakeKeypair)
    monkeypatch.setattr(relayer_module, "TransactionEnvelope", _FakeTransactionEnvelope)
    monkeypatch.setattr(relayer_module, "TransactionBuilder", _FakeTransactionBuilder)
    monkeypatch.setattr(settings, "RELAYER_SECRET_KEY", "SFAKESECRET")
    yield
    monkeypatch.setattr(settings, "RELAYER_SECRET_KEY", "")


def test_submit_signed_transaction_succeeds(monkeypatch):
    monkeypatch.setattr(
        relayer_module,
        "SorobanServer",
        lambda url: _FakeSorobanServer(get_statuses=["SUCCESS"]),
    )

    result = submit_signed_transaction("fake-xdr", poll_interval_seconds=0)

    assert result.success is True
    assert result.hash == "fakehash"
    assert result.error is None


def test_submit_signed_transaction_reports_onchain_failure(monkeypatch):
    monkeypatch.setattr(
        relayer_module,
        "SorobanServer",
        lambda url: _FakeSorobanServer(get_statuses=["FAILED"]),
    )

    result = submit_signed_transaction("fake-xdr", poll_interval_seconds=0)

    assert result.success is False
    assert result.hash == "fakehash"
    assert "failed" in result.error.lower()


def test_submit_signed_transaction_reports_send_rejection(monkeypatch):
    monkeypatch.setattr(
        relayer_module,
        "SorobanServer",
        lambda url: _FakeSorobanServer(send_status="ERROR"),
    )

    result = submit_signed_transaction("fake-xdr", poll_interval_seconds=0)

    assert result.success is False
    assert result.hash is None


def test_submit_signed_transaction_times_out(monkeypatch):
    monkeypatch.setattr(
        relayer_module,
        "SorobanServer",
        lambda url: _FakeSorobanServer(get_statuses=[]),
    )

    result = submit_signed_transaction(
        "fake-xdr", poll_interval_seconds=0, poll_timeout_seconds=0
    )

    assert result.success is False
    assert "timed out" in result.error.lower()


def test_submit_signed_transaction_requires_relayer_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "RELAYER_SECRET_KEY", "")

    with pytest.raises(RelayerNotConfiguredError):
        submit_signed_transaction("fake-xdr")

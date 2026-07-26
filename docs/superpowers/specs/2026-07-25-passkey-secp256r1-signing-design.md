# Passkey-Based Transaction Signing via Secp256r1 — Design

Implements issue #18: adds passkey (WebAuthn/Secp256r1) signing as an
alternative to Freighter for mint/burn transactions, testnet-only.

## Research Spike Findings

(Also posted as a comment on issue #18, per its acceptance criteria.)

Passkey signing on Stellar is **not** "sign a normal transaction with a
fingerprint instead of a private key" — Protocol 21's Secp256r1 support
(CAP-0051) is verified inside a **Soroban smart-wallet contract**, a
fundamentally different address (`C...`) from a user's classic Ed25519
account (`G...`, e.g. their existing Freighter address). There's no way to
"passkey-sign" an existing classic account; passkey signing means creating
a new smart-wallet contract per user and authorizing through it instead.

The relevant SDK is [`passkey-kit`](https://github.com/kalepail/passkey-kit)
(npm `passkey-kit`, peer dep `@stellar/stellar-sdk >= 16.0.0`). Its
`PasskeyKit` browser client runs the WebAuthn ceremony, deterministically
derives the wallet's contract address from the passkey's credential id,
and builds/signs Soroban auth entries with the passkey. Its `PasskeyServer`
+ relayer path (submission) is built around a paid third-party service
(OpenZeppelin Relayer Channels) plus a Cloudflare Worker proxy — the smart
wallet holds no XLM, so something has to pay transaction fees, and that's
passkey-kit's default answer to "something."

Good news: `mint`/`burn` in `contract/synthetic-xau/src/lib.rs` already call
`user.require_auth()` on a generic `Address` — this works identically
whether `user` is a classic account or a smart-wallet contract, so **no
Aurum contract changes are needed**. The collateral-token balance and
position tracking are keyed off that same `Address`, so a passkey wallet
is a genuinely fresh position, not a new signing method for an existing
one — consistent with "no Freighter needed," but worth being explicit
that it doesn't carry over an existing Freighter position.

## Decisions

- **Fee sponsorship:** self-hosted, not OpenZeppelin Relayer Channels. A
  new backend endpoint takes a passkey-signed transaction, fee-bumps it
  with a backend-held funded testnet keypair (`stellar-sdk` Python
  package, already a backend dependency), and submits it via
  `SorobanServer`. Avoids a third-party paid dependency and keeps the
  whole flow inspectable in this repo.
- **Mint/burn form:** built as part of this issue, since none currently
  exists. Minimal: collateral amount + mint amount inputs, Mint/Burn
  buttons, working with whichever wallet (Freighter or passkey) is
  connected.
- **Scope:** testnet only. `networkPassphrase`/`rpcUrl`/`walletWasmHash`
  are hardcoded testnet values; no network switcher. Mainnet is
  explicitly deferred (per the issue).

## New/Changed Files

- `frontend/lib/passkey.ts` (new) — thin wrapper around `PasskeyKit`:
  - `isPasskeySupported(): boolean` — feature-checks
    `window.PublicKeyCredential`, used for graceful Freighter fallback.
  - `createPasskeyWallet(appName, userLabel)` — runs `createKey`, submits
    the resulting deploy transaction through the backend relayer, returns
    `{ contractId, keyId }`.
  - `connectPasskeyWallet()` — `PasskeyKit.connectWallet()`, returns
    `{ contractId, keyId }` or throws if no wallet is found.
  - `signAndSubmit(assembledTx)` — `kit.sign(tx)` then posts the signed
    XDR to `POST /relayer/submit`, returns the transaction result.
- `frontend/components/WalletConnect.tsx` (new) — extracts the
  wallet-connection header block currently inlined in `page.tsx` into its
  own component; renders "Connect Freighter" (existing behavior) and,
  when `isPasskeySupported()`, a "Sign in with passkey" button. Reports
  the connected wallet back to the parent as
  `{ kind: "freighter" | "passkey", address: string }`.
- `frontend/app/page.tsx` (modified) — replaces the inlined wallet header
  with `<WalletConnect />`; adds a minimal mint/burn form section (amount
  inputs + Mint/Burn buttons) that signs via whichever wallet kind is
  connected.
- `backend/app/services/relayer.py` (new) — `submit_signed_transaction(xdr: str) -> RelayerResult`:
  parses the incoming envelope, wraps it in a fee-bump transaction paid by
  `settings.RELAYER_SECRET_KEY`, submits via `SorobanServer`, polls for
  completion, returns a small result model (`hash`, `success`, `error`).
- `backend/app/api/routes/relayer.py` (new) — `POST /relayer/submit`
  taking `{ xdr: str }`, calling the service, returning its result.
  Testnet-only: rejects if `settings.RELAYER_SECRET_KEY` is unset, rather
  than silently no-op'ing.
- `backend/app/core/config.py` (modified) — adds `RELAYER_SECRET_KEY: str = ""`.
- `frontend/package.json` (modified) — adds `passkey-kit` and
  `@stellar/stellar-sdk` dependencies.

## Fallback Behavior

`WalletConnect` checks `isPasskeySupported()` on mount (feature-detects
`window.PublicKeyCredential` and, where available,
`isUserVerifyingPlatformAuthenticatorAvailable()`). If unsupported, the
passkey button is omitted entirely and Freighter is the only option —
matching the issue's "falls back gracefully" criterion without needing a
runtime error path (there's nothing to fall back *from* if the button
never appears).

## Testing

- `frontend/lib/passkey.ts`: unit tests mocking `PasskeyKit` — wallet
  creation/connection happy path, `isPasskeySupported` true/false branches.
- `backend/app/services/relayer.py`: unit tests with a fake
  `SorobanServer` — successful submission, submission failure surfaced as
  `success: false` rather than raising, missing `RELAYER_SECRET_KEY`
  rejected clearly.
- `backend/app/api/routes/relayer.py`: route test hitting `POST
  /relayer/submit` with the fake service override, matching the existing
  route-test pattern in this repo.
- No live-network integration test for wallet creation (would require a
  real WebAuthn authenticator, not available in CI) — covered by mocking
  `PasskeyKit` at the module boundary instead.

## Out of Scope

- OpenZeppelin Relayer Channels / passkey-kit's `PasskeyServer`.
- Mainnet configuration of any kind.
- Migrating an existing Freighter position to a passkey wallet.
- Multi-signer wallet management (add/remove signers) — only the initial
  passkey-only wallet creation and signing path.

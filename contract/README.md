# Aurum — SyntheticXAU Contract

Over-collateralized synthetic gold (XAU) exposure on Soroban.

## ⚠️ Not audited

This contract has not been professionally audited. See [`docs/risks.md`](../docs/risks.md) before using it beyond testnet. Known simplifications in this reference implementation (tracked as open issues, not hidden):

- **Off-chain price push** rather than a direct on-chain oracle contract call (Reflector/DIA integration is a tracked "high" complexity issue).
- **Full liquidation only** — a liquidator takes 100% of a position's collateral rather than a partial, proportional liquidation. Partial liquidation (closer to production lending protocol design) is a tracked issue.
- **No liquidation bonus parameter yet** — the liquidator currently receives all collateral with no separate "repay debt, keep bonus" step modeled on-chain; this is a simplification flagged for follow-up.
- **All approved collateral tokens are treated as 1:1 USD-pegged**, and `Position` doesn't record which specific token(s) contributed to its `collateral` total — there's no per-token price feed. `mint` checks the token it's given against `Config.approved_collateral_tokens`, but `burn` and `liquidate` also just take a `collateral_token` argument from the caller and trust it: the contract verifies that token is *approved*, not that it matches what a given position actually deposited. This is safe as long as a position sticks to one collateral token in practice, but isn't enforced on-chain — a stronger design would lock the token in at first `mint` and reject mismatches on subsequent calls. Tracked as a follow-up.

## Layout

| File | Responsibility |
|---|---|
| `src/lib.rs` | Contract entrypoints: `initialize`, `push_price`, `mint`, `burn`, `get_position_health`, `liquidate` |
| `src/types.rs` | Storage structs (`Config`, `Position`) and storage helpers (note: writes extend TTL — see comment in `set_position`) |
| `src/errors.rs` | Typed `AurumError` enum |
| `src/pricing.rs` | Pure collateral-ratio math, unit tested independently of the contract env |
| `src/test.rs` | Integration tests covering mint/burn/liquidate flows against a mock Stellar Asset Contract |

## Deploying to testnet

```bash
# Build a deployable WASM (stellar-cli uses the wasm32v1-none target)
stellar contract build

# Deploy to testnet
stellar contract deploy \
  --wasm target/wasm32v1-none/release/aurum_synthetic_xau.wasm \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet
```

**Latest testnet deployment:** `CDDOQRCE5LNJQBELCCRWSQGZR6U2WM6SZDUAUABSURIKUVEEOKP7QW6F`

# Architecture

## Overview

Aurum has three pieces:

1. **Contract** (`contract/synthetic-xau/`) — the `SyntheticXau` Soroban
   contract: `initialize`, `push_price`, `mint`, `burn`, `get_price`,
   `get_position_health`, and `liquidate`. See
   [`docs/contract.md`](contract.md) for the method-by-method reference.
2. **Backend** (`backend/`) — FastAPI service with:
   - `app/services/oracle.py` — median price aggregation across sources,
     and deviation reconciliation against real spot XAUUSD. Fully unit
     tested with no live network dependency.
   - `app/services/feeds.py` — fetches live XAU/USD quotes from the
     Reflector (SEP-40 `lastprice`) and DIA (`get_value`) Soroban oracle
     contracts and constructs the `PriceQuote` objects `oracle.py`
     consumes.
   - `app/services/repository.py` — Supabase persistence layer for
     reconciliation history snapshots (`price_history` table).
   - `app/services/sessions.py` — trading session detection (Asia /
     London / New York) used to add context to deviation readings.
   - `app/api/routes/` — `/pricing`, `/positions`, `/health`.
3. **Frontend** (`frontend/`) — Next.js dashboard: a reconciliation card
   with a live deviation meter, a position card that recalculates
   collateral ratio from the entered spot price, a position history
   chart, a live trading-session badge, and Freighter wallet
   connect/disconnect.

## Data flow

```
User enters on-chain price + spot price in dashboard
        │
        ▼
POST /pricing/reconcile
        │
        ▼
oracle.reconcile_with_spot()
  - computes deviation in bps
  - flags if above DEVIATION_ALERT_THRESHOLD_BPS
  - tags the current trading session (sessions.py)
        │
        ├─────────────────────────────────────────┐
        ▼                                         ▼
ReconciliationReport                     repository.record_price()
        │                                         │
        ▼                                         ▼
ReconciliationCard renders it            Supabase price_history table
```

## Price history persistence (Supabase)

Spot-reconciliation checks are persisted to Supabase to power historical
deviation charts on the dashboard.

### Schema (`price_history`)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `bigint` | `generated always as identity primary key` | Unique row identifier |
| `on_chain_price_usd` | `double precision` | `not null` | Aggregated on-chain price (USD) |
| `spot_price_usd` | `double precision` | `not null` | Reference spot price (USD) |
| `deviation_bps` | `double precision` | `not null` | Absolute price deviation in basis points |
| `trading_session` | `text` | `not null` | Trading session (`asia`, `london`, `new_york`, `off_hours`) |
| `recorded_at` | `timestamptz` | `not null default timezone('utc'::text, now())` | Snapshot timestamp (UTC) |

Indexed on `recorded_at desc` (`idx_price_history_recorded_at_desc`) for
efficient chronological retrieval.

Migration SQL is located in `supabase/migrations/20261004000000_create_price_history.sql`.

### Endpoints

- `POST /pricing/reconcile` — computes deviation against spot and inserts
  a new snapshot into `price_history`.
- `GET /pricing/history?limit=100` — retrieves historical records ordered
  by `recorded_at` descending.


## Oracle aggregation

`oracle.aggregate_median()` takes a list of `PriceQuote` objects and
returns their median. `app/services/feeds.py` produces real
`PriceQuote`s by calling the Reflector and DIA Soroban oracle contracts
directly. `POST /pricing/aggregate` currently accepts manually-supplied
quotes in its request body rather than calling `feeds.py` itself — the
two are decoupled so the aggregation math has no network dependency in
tests.

## Positions

`/positions/` stores position summaries in memory, keyed by address. It
exposes a `GET /positions/{address}` read and a `POST /positions/`
upsert. It does not read position state from the deployed contract.

## Frontend

The dashboard's price inputs are entered manually and reconciled on
demand via a "Check deviation" button rather than refreshed
automatically. Freighter wallet integration covers connect and
disconnect; the dashboard does not yet submit `mint`, `burn`, or
`liquidate` transactions.

## Design rationale

- **Aggregation math separated from data fetching.** `oracle.py` is
  pure and fully testable without hitting any live oracle or needing
  API keys in CI. `feeds.py` is the network-dependent layer, isolated
  so it can be tested against a fake Soroban RPC server instead of a
  live testnet contract.
- **Off-chain price push in the contract, not on-chain oracle reads.**
  The contract calls no other contract for pricing. An authorized
  price-pusher account — the backend — supplies the XAU/USD price
  directly via `push_price`, which keeps the contract's surface area
  small and auditable.

## Roadmap

- Wire `app/services/feeds.py` into `POST /pricing/aggregate` so the
  route runs on live Reflector/DIA quotes instead of manually-supplied
  ones.
- Real spot-price API integration, replacing the
  `SPOT_PRICE_PROVIDER=manual` configuration value.
- Soroban RPC reads for `/positions/`, replacing the in-memory store
  and removing the client-writable `POST` endpoint.
- Wallet transaction submission — `mint`, `burn`, and `liquidate` from
  the frontend via Freighter.
- Auto-refreshing reconciliation, replacing the manual "Check
  deviation" button.
- Partial liquidation in the contract, replacing full-collateral
  liquidation.

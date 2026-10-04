-- Migration: Create price_history table for persisting oracle reconciliation snapshots
-- Reference: Issue #26

create table if not exists public.price_history (
    id bigint generated always as identity primary key,
    on_chain_price_usd double precision not null,
    spot_price_usd double precision not null,
    deviation_bps double precision not null,
    trading_session text not null,
    recorded_at timestamptz not null default timezone('utc'::text, now())
);

-- Index for descending chronological queries (used by GET /pricing/history)
create index if not exists idx_price_history_recorded_at_desc
    on public.price_history (recorded_at desc);

-- Enable Row Level Security (RLS)
alter table public.price_history enable row level security;

-- Allow public read access to price history for dashboard charts
create policy "Allow public read access to price history"
    on public.price_history
    for select
    using (true);

-- Allow backend service role insert access
create policy "Allow service insert access to price history"
    on public.price_history
    for insert
    with check (true);

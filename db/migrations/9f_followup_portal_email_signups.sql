-- Portal email signups (from /vacation, /fashion בקרוב pages)
-- Anonymous inserts allowed (no auth required for signup)
create table if not exists public.portal_email_signups (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  vertical text not null check (vertical in ('vacation', 'fashion')),
  created_at timestamptz not null default now(),
  user_agent text,
  referrer text
);

create index if not exists portal_email_signups_email_idx on public.portal_email_signups (email);
create index if not exists portal_email_signups_created_at_idx on public.portal_email_signups (created_at desc);

-- RLS: anonymous can insert, only authenticated admins can read
alter table public.portal_email_signups enable row level security;

create policy "Anyone can insert email signups"
  on public.portal_email_signups
  for insert
  to anon, authenticated
  with check (true);

-- Future-proof for Supabase Data API default change (May 30 / Oct 30 cutoff)
grant insert on public.portal_email_signups to anon;
grant insert on public.portal_email_signups to authenticated;
grant select on public.portal_email_signups to service_role;

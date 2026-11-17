-- 치이카와 위시 도감: 계정별 기록 저장 표
create table if not exists public.dogam (
  user_id uuid primary key references auth.users(id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz default now()
);
alter table public.dogam enable row level security;
-- 여러 번 실행해도 에러 안 나게: 있던 규칙은 지우고 다시 만듦
drop policy if exists "dogam_select_own" on public.dogam;
drop policy if exists "dogam_insert_own" on public.dogam;
drop policy if exists "dogam_update_own" on public.dogam;
create policy "dogam_select_own" on public.dogam for select using (auth.uid() = user_id);
create policy "dogam_insert_own" on public.dogam for insert with check (auth.uid() = user_id);
create policy "dogam_update_own" on public.dogam for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

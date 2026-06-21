-- Run this after the initial schema.
-- It allows both logged-in and non-logged-in visitors to save public comments,
-- board posts, and game scores in the server database.

alter table public.article_comments
  alter column user_id drop not null,
  add column if not exists author_name text not null default '익명';

alter table public.board_posts
  alter column user_id drop not null,
  add column if not exists author_name text not null default '익명';

alter table public.game_scores
  alter column user_id drop not null,
  add column if not exists author_name text not null default '익명';

create table if not exists public.problem_reports (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete set null,
  author_name text not null default '익명',
  source text not null default 'unknown',
  mode text,
  article_key text,
  question text not null,
  answer text,
  reference_text text,
  detail text not null,
  page_url text,
  context jsonb not null default '{}'::jsonb,
  status text not null default 'open',
  created_at timestamptz not null default now()
);

alter table public.problem_reports
  add column if not exists user_id uuid references auth.users(id) on delete set null,
  add column if not exists author_name text not null default '익명',
  add column if not exists source text not null default 'unknown',
  add column if not exists mode text,
  add column if not exists article_key text,
  add column if not exists question text not null default '',
  add column if not exists answer text,
  add column if not exists reference_text text,
  add column if not exists detail text not null default '',
  add column if not exists page_url text,
  add column if not exists context jsonb not null default '{}'::jsonb,
  add column if not exists status text not null default 'open',
  add column if not exists created_at timestamptz not null default now();

alter table public.problem_reports enable row level security;

drop policy if exists "users create own comments" on public.article_comments;
drop policy if exists "users create own board posts" on public.board_posts;
drop policy if exists "users create own scores" on public.game_scores;
drop policy if exists "scores are readable" on public.game_scores;
drop policy if exists "anyone can create problem reports" on public.problem_reports;

create policy "anyone can create comments"
on public.article_comments for insert
with check (user_id is null or auth.uid() = user_id);

create policy "anyone can create board posts"
on public.board_posts for insert
with check (user_id is null or auth.uid() = user_id);

create policy "anyone can create scores"
on public.game_scores for insert
with check (user_id is null or auth.uid() = user_id);

create policy "scores are readable"
on public.game_scores for select
using (true);

create policy "anyone can create problem reports"
on public.problem_reports for insert
with check (user_id is null or auth.uid() = user_id);

grant insert on public.article_comments to anon;
grant insert on public.board_posts to anon;
grant select, insert on public.game_scores to anon, authenticated;
grant insert on public.problem_reports to anon, authenticated;

grant usage, select on all sequences in schema public to anon, authenticated;

alter default privileges in schema public
grant usage, select on sequences to anon, authenticated;

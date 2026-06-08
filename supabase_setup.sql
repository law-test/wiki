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

drop policy if exists "users create own comments" on public.article_comments;
drop policy if exists "users create own board posts" on public.board_posts;
drop policy if exists "users create own scores" on public.game_scores;

create policy "anyone can create comments"
on public.article_comments for insert
with check (user_id is null or auth.uid() = user_id);

create policy "anyone can create board posts"
on public.board_posts for insert
with check (user_id is null or auth.uid() = user_id);

create policy "anyone can create scores"
on public.game_scores for insert
with check (user_id is null or auth.uid() = user_id);

grant insert on public.article_comments to anon;
grant insert on public.board_posts to anon;
grant insert on public.game_scores to anon;

grant usage, select on all sequences in schema public to anon, authenticated;

alter default privileges in schema public
grant usage, select on sequences to anon, authenticated;

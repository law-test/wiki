create extension if not exists pgcrypto;

create table if not exists public.private_game_questions (
  id uuid primary key default gen_random_uuid(),
  bank text not null check (bank in ('clat', 'ethics')),
  source_pid text not null,
  source_variant text not null default 'base',
  subject text,
  law_name text,
  article text,
  article_norms text[] not null default '{}'::text[],
  topic text,
  prompt text not null,
  answer text not null check (answer in ('O', 'X')),
  explanation text,
  reference_text text,
  corrected_prompt text,
  grade text,
  weight numeric not null default 0,
  freq integer not null default 1,
  tags text,
  meta jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (bank, source_pid, source_variant)
);

create index if not exists private_game_questions_bank_subject_idx
  on public.private_game_questions (bank, subject)
  where active;

create index if not exists private_game_questions_article_norms_idx
  on public.private_game_questions using gin (article_norms)
  where active;

create or replace function public.set_private_game_questions_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_private_game_questions_updated_at
  on public.private_game_questions;

create trigger set_private_game_questions_updated_at
before update on public.private_game_questions
for each row
execute function public.set_private_game_questions_updated_at();

alter table public.private_game_questions enable row level security;
revoke all on public.private_game_questions from anon, authenticated;

create or replace function public.get_private_game_questions(
  p_bank text,
  p_subject text default null,
  p_limit integer default 80
)
returns table (
  question_id uuid,
  prompt text,
  subject text,
  topic text,
  grade text,
  weight numeric,
  freq integer,
  tags text,
  article text
)
language sql
volatile
security definer
set search_path = public
as $$
  select
    q.id,
    q.prompt,
    q.subject,
    q.topic,
    q.grade,
    q.weight,
    q.freq,
    q.tags,
    q.article
  from public.private_game_questions q
  where q.active
    and q.bank = p_bank
    and (
      p_subject is null
      or p_subject = ''
      or p_subject = 'all'
      or q.subject = p_subject
    )
  order by
    (-ln(greatest(random(), 0.000001))
      / greatest((coalesce(q.weight, 0) + 1) * greatest(q.freq, 1), 0.01))
  limit least(greatest(coalesce(p_limit, 80), 1), 300);
$$;

create or replace function public.grade_private_game_question(
  p_question_id uuid,
  p_answer text
)
returns table (
  question_id uuid,
  correct boolean,
  answer text,
  explanation text,
  reference_text text,
  article text,
  corrected_prompt text,
  topic text,
  grade text,
  tags text,
  freq integer
)
language sql
stable
security definer
set search_path = public
as $$
  select
    q.id,
    upper(trim(coalesce(p_answer, ''))) = q.answer,
    q.answer,
    q.explanation,
    q.reference_text,
    q.article,
    q.corrected_prompt,
    q.topic,
    q.grade,
    q.tags,
    q.freq
  from public.private_game_questions q
  where q.active
    and q.id = p_question_id
  limit 1;
$$;

create or replace function public.get_private_typing_prompts(
  p_limit integer default 500
)
returns table (
  question_id uuid,
  prompt text,
  subject text,
  tags text
)
language sql
volatile
security definer
set search_path = public
as $$
  select q.id, q.prompt, q.subject, q.tags
  from public.private_game_questions q
  where q.active
    and q.bank = 'clat'
    and q.answer = 'O'
    and length(q.prompt) between 18 and 260
  order by random()
  limit least(greatest(coalesce(p_limit, 500), 1), 1000);
$$;

create or replace function public.get_private_article_atoms(
  p_subject text,
  p_law_name text,
  p_article text,
  p_limit integer default 8
)
returns table (
  question_id uuid,
  family_id text,
  variant text,
  prompt text,
  answer text,
  subject text,
  topic text,
  explanation text,
  reference_text text,
  article text,
  corrected_prompt text,
  grade text,
  weight numeric,
  freq integer,
  tags text
)
language sql
stable
security definer
set search_path = public
as $$
  with matched as (
    select q.*
    from public.private_game_questions q
    where q.active
      and q.bank in ('clat', 'ethics')
      and (
        p_subject is null
        or p_subject = ''
        or q.subject = p_subject
        or q.law_name = p_law_name
      )
      and (
        q.article_norms @> array[p_article]
        or q.article ilike '%' || p_article || '%'
      )
    order by q.freq desc, q.weight desc, q.source_pid, q.source_variant
    limit least(greatest(coalesce(p_limit, 8), 1), 30)
  )
  select
    id,
    source_pid,
    source_variant,
    prompt,
    answer,
    subject,
    topic,
    explanation,
    reference_text,
    article,
    corrected_prompt,
    grade,
    weight,
    freq,
    tags
  from matched;
$$;

grant execute on function public.get_private_game_questions(text, text, integer) to anon, authenticated;
grant execute on function public.grade_private_game_question(uuid, text) to anon, authenticated;
grant execute on function public.get_private_typing_prompts(integer) to anon, authenticated;
grant execute on function public.get_private_article_atoms(text, text, text, integer) to anon, authenticated;

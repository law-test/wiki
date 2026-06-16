from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "index.html"
DEFAULT_OUT = ROOT / "migration_out"
SUPABASE_URL = "https://vtqbyznczhgkpylczxpe.supabase.co"


SECTION_RE = re.compile(
    r"<section\b(?=[^>]*\bclass=(['\"])[^'\"]*\bart\b[^'\"]*\1)(?P<attrs>[^>]*)>(?P<html>.*?)</section>",
    re.I | re.S,
)
ATTR_RE = re.compile(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean_space(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ").replace("\u3000", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    return value.strip()


def strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    value = re.sub(r"</p\s*>", "\n", value, flags=re.I)
    return clean_space(TAG_RE.sub("", value))


def attrs_to_dict(raw: str) -> dict[str, str]:
    return {name: html.unescape(value) for name, _, value in ATTR_RE.findall(raw or "")}


def extract_first(pattern: str, source: str, flags: int = re.I | re.S) -> str:
    match = re.search(pattern, source or "", flags)
    if not match:
        return ""
    return match.group(match.lastindex or 0).strip()


def article_sort(article_no: str) -> tuple[int, int]:
    match = re.search(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", article_no or "")
    if not match:
        return (999999, 0)
    return int(match.group(1)), int(match.group(2) or 0)


def article_code(article_no: str) -> str:
    base, sub = article_sort(article_no)
    return f"{base:04d}{sub:02d}"


def extract_lawtext(section_html: str) -> str:
    match = re.search(
        r"<div[^>]*class=(['\"])[^'\"]*\blawtext\b[^'\"]*\1[^>]*>(?P<body>.*?)(?=\s*<h2\b|\s*</section>)",
        section_html,
        re.I | re.S,
    )
    if not match:
        return ""
    body_html = match.group("body")
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", body_html, re.I | re.S)
    if paragraphs:
        return "\n".join(strip_tags(paragraph) for paragraph in paragraphs if strip_tags(paragraph))
    lines = [line for line in strip_tags(body_html).splitlines() if line and line != "조문"]
    return "\n".join(lines)


def sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def extract_legacy_civil_sections(index_path: Path) -> list[dict[str, Any]]:
    text = index_path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for match in SECTION_RE.finditer(text):
        attrs = attrs_to_dict(match.group("attrs"))
        data_art = clean_space(attrs.get("data-art", ""))
        data_pyeon = clean_space(attrs.get("data-pyeon", ""))
        if not data_art.startswith("제") or not data_pyeon.startswith("제"):
            continue
        section_html = "<section" + match.group("attrs") + ">" + match.group("html") + "</section>"
        h1_html = extract_first(r"<h1[^>]*>(.*?)</h1>", section_html)
        h1_text = strip_tags(h1_html)
        title_match = re.search(r"\((.*?)\)", h1_text)
        title = clean_space(title_match.group(1) if title_match else h1_text)
        crumb_text = strip_tags(extract_first(r"<div[^>]*class=(['\"])[^'\"]*\bcrumb\b[^'\"]*\1[^>]*>(.*?)</div>", section_html))
        if not crumb_text:
            crumb_text = data_pyeon
        crumb_parts = [clean_space(part) for part in re.split(r"\s*[›>]\s*", crumb_text) if clean_space(part)]
        lawtext = extract_lawtext(section_html)
        base, sub = article_sort(data_art)
        rows.append(
            {
                "id": f"민법:민법:{data_art}",
                "subject": "민법",
                "law_name": "민법",
                "article_no": data_art,
                "article_code": article_code(data_art),
                "title": title,
                "body": lawtext,
                "part": crumb_parts[0] if len(crumb_parts) > 0 else data_pyeon,
                "chapter": crumb_parts[1] if len(crumb_parts) > 1 else None,
                "section": crumb_parts[2] if len(crumb_parts) > 2 else None,
                "source": "index.html legacy civil article",
                "source_url": "https://www.law.go.kr/법령/민법",
                "sort_base": base,
                "sort_sub": sub,
                "crumb": " > ".join(crumb_parts),
                "html": section_html,
            }
        )
    rows.sort(key=lambda row: (row["sort_base"], row["sort_sub"], row["article_no"]))
    return rows


def article_sql_values(row: dict[str, Any]) -> str:
    cols = [
        "id",
        "subject",
        "law_name",
        "article_no",
        "article_code",
        "title",
        "body",
        "part",
        "chapter",
        "section",
        "source",
        "source_url",
        "sort_base",
        "sort_sub",
    ]
    return "(" + ", ".join(sql_literal(row.get(col)) for col in cols) + ")"


def page_sql_values(row: dict[str, Any]) -> str:
    cols = ["id", "subject", "article_no", "title", "part", "chapter", "section", "crumb", "html"]
    return "(" + ", ".join(sql_literal(row.get(col)) for col in cols) + ")"


def write_sql_chunks(rows: list[dict[str, Any]], sql_dir: Path) -> None:
    sql_dir.mkdir(parents=True, exist_ok=True)
    article_columns = (
        "id, subject, law_name, article_no, article_code, title, body, part, chapter, section, "
        "source, source_url, sort_base, sort_sub"
    )
    page_columns = "id, subject, article_no, title, part, chapter, section, crumb, html"

    schema = """create table if not exists public.law_article_pages (
  id text primary key,
  subject text not null,
  article_no text not null,
  title text not null,
  part text,
  chapter text,
  section text,
  crumb text,
  html text not null,
  updated_at timestamptz not null default now()
);

alter table public.law_article_pages enable row level security;

drop policy if exists "law article pages are readable" on public.law_article_pages;

create policy "law article pages are readable"
on public.law_article_pages for select
using (true);

grant select on public.law_article_pages to anon, authenticated;
grant insert, update on public.law_article_pages to authenticated;

select 'law_article_pages_schema_ready' as status;
"""
    (sql_dir / "00_law_article_pages_schema.sql").write_text(schema, encoding="utf-8")

    for idx, group in enumerate(chunked(rows, 80), start=1):
        values = ",\n".join(article_sql_values(row) for row in group)
        sql = f"""insert into public.law_subject_articles ({article_columns})
values
{values}
on conflict (id) do update set
  subject = excluded.subject,
  law_name = excluded.law_name,
  article_no = excluded.article_no,
  article_code = excluded.article_code,
  title = excluded.title,
  body = excluded.body,
  part = excluded.part,
  chapter = excluded.chapter,
  section = excluded.section,
  source = excluded.source,
  source_url = excluded.source_url,
  sort_base = excluded.sort_base,
  sort_sub = excluded.sort_sub;

select 'civil_law_subject_articles_{idx:03d}_done' as status;
"""
        (sql_dir / f"civil_law_subject_articles_{idx:03d}.sql").write_text(sql, encoding="utf-8")

    for idx, group in enumerate(chunked(rows, 20), start=1):
        values = ",\n".join(page_sql_values(row) for row in group)
        sql = f"""insert into public.law_article_pages ({page_columns})
values
{values}
on conflict (id) do update set
  subject = excluded.subject,
  article_no = excluded.article_no,
  title = excluded.title,
  part = excluded.part,
  chapter = excluded.chapter,
  section = excluded.section,
  crumb = excluded.crumb,
  html = excluded.html,
  updated_at = now();

select 'civil_law_article_pages_{idx:03d}_done' as status;
"""
        (sql_dir / f"civil_law_article_pages_{idx:03d}.sql").write_text(sql, encoding="utf-8")


def write_outputs(rows: list[dict[str, Any]], out_dir: Path, index_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sql_dir = out_dir / "sql"
    (out_dir / "civil_law_legacy_sections.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_sql_chunks(rows, sql_dir)
    report = [
        "# index.html legacy data audit",
        "",
        f"- source: `{index_path}`",
        f"- legacy civil article sections: {len(rows)}",
        f"- first article: {rows[0]['article_no'] if rows else '-'}",
        f"- last article: {rows[-1]['article_no'] if rows else '-'}",
        f"- SQL chunks for `law_subject_articles`: {len(list(sql_dir.glob('civil_law_subject_articles_*.sql')))}",
        f"- SQL chunks for `law_article_pages`: {len(list(sql_dir.glob('civil_law_article_pages_*.sql')))}",
        "",
        "## Next",
        "",
        "1. Run `00_law_article_pages_schema.sql` once if full legacy page HTML should be stored in DB.",
        "2. Import `civil_law_subject_articles_*.sql` to move 민법 조문 text into `law_subject_articles`.",
        "3. Import `civil_law_article_pages_*.sql` to preserve the old full article-page HTML.",
        "4. After DB read is verified, delete the static civil article sections from `index.html` and load them consistently from DB.",
    ]
    (out_dir / "index_legacy_data_audit.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def supabase_request(method: str, path: str, key: str, payload: Any | None = None) -> tuple[int, str]:
    body = None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(SUPABASE_URL + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def import_to_supabase(rows: list[dict[str, Any]], key: str) -> None:
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY or LAW_TEST_SUPABASE_KEY is required for DB import.")
    article_records = [
        {
            key_: row.get(key_)
            for key_ in (
                "id",
                "subject",
                "law_name",
                "article_no",
                "article_code",
                "title",
                "body",
                "part",
                "chapter",
                "section",
                "source",
                "source_url",
                "sort_base",
                "sort_sub",
            )
        }
        for row in rows
    ]
    page_records = [
        {
            key_: row.get(key_)
            for key_ in ("id", "subject", "article_no", "title", "part", "chapter", "section", "crumb", "html")
        }
        for row in rows
    ]

    status, text = supabase_request("POST", "/rest/v1/law_subject_articles?on_conflict=id", key, [])
    if status >= 400:
        raise SystemExit(
            "DB write permission check failed. Use a service-role key or run the generated SQL in Supabase.\n"
            f"Supabase response: {status} {text}"
        )

    for group in chunked(article_records, 100):
        status, text = supabase_request("POST", "/rest/v1/law_subject_articles?on_conflict=id", key, group)
        if status >= 400:
            raise SystemExit(f"law_subject_articles import failed: {status} {text}")
    for group in chunked(page_records, 25):
        status, text = supabase_request("POST", "/rest/v1/law_article_pages?on_conflict=id", key, group)
        if status >= 400:
            raise SystemExit(f"law_article_pages import failed: {status} {text}")
    print(f"Imported {len(rows)} civil-law legacy sections to Supabase.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and migrate legacy civil-law sections embedded in index.html.")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Path to index.html")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Directory for generated JSON/SQL/report files")
    parser.add_argument("--import-db", action="store_true", help="Import generated records to Supabase with a write key")
    args = parser.parse_args()

    index_path = Path(args.index)
    out_dir = Path(args.out)
    rows = extract_legacy_civil_sections(index_path)
    if not rows:
        raise SystemExit("No legacy civil-law article sections were found.")
    write_outputs(rows, out_dir, index_path)
    print(f"Found {len(rows)} legacy civil-law article sections in {index_path}.")
    print(f"Wrote migration files to {out_dir}.")
    if args.import_db:
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("LAW_TEST_SUPABASE_KEY")
        import_to_supabase(rows, key or "")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT.parent / "law-test-private" / "civil_special_laws"
SOURCE = Path.home() / "Downloads" / "민사특별법_민법조문_매칭_민간임대_공동주택_소비자_가맹거래추가.txt"
JSON_OUT = OUT_DIR / "civil_special_laws.json"
SQL_OUT = OUT_DIR / "supabase_civil_special_laws.sql"
SQL_ASCII_OUT = OUT_DIR / "supabase_civil_special_laws_ascii.sql"


def sql_quote(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def ascii_sql_literal(value: str | None) -> str:
    if value is None:
        return "null"
    escaped = value.replace("\\", "\\\\").replace("'", "''")
    return "convert_from(decode('" + escaped.encode("utf-8").hex() + "','hex'),'UTF8')"


def slugify(value: str) -> str:
    base = re.sub(r"[^0-9A-Za-z가-힣]+", "-", value).strip("-")
    return base or "special-law"


def parse_rows() -> list[dict[str, str]]:
    text = SOURCE.read_text(encoding="utf-8")
    pattern = re.compile(r"^(.+?) - (제\d+조(?:의\d+)?)\(([^)]+)\) : (.+)$")
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        group, civil_article, civil_title, law_name = m.groups()
        short_name = ""
        if law_name.endswith(")") and "(" in law_name:
            alias = law_name.rsplit("(", 1)[1][:-1].strip()
            if alias and len(alias) <= 12:
                short_name = alias
        rows.append(
            {
                "id": f"민사특별법-{civil_article}-{len(rows) + 1}",
                "civil_article": civil_article,
                "civil_article_title": civil_title,
                "category": group,
                "law_name": law_name,
                "short_name": short_name,
                "source_url": "https://www.law.go.kr/LSW/lsSc.do?menuId=1&subMenuId=15&query=" + law_name,
                "slug": slugify(short_name or law_name),
                "sort_order": f"{len(rows) + 1:04d}",
            }
        )
    return rows


def build_sql(rows: list[dict[str, str]], ascii_only: bool = False) -> str:
    lit = ascii_sql_literal if ascii_only else sql_quote
    values = []
    for row in rows:
        values.append(
            "("
            + ", ".join(
                [
                    lit(row["id"]),
                    lit(row["civil_article"]),
                    lit(row["civil_article_title"]),
                    lit(row["category"]),
                    lit(row["law_name"]),
                    lit(row["short_name"]),
                    lit(row["source_url"]),
                    lit(row["slug"]),
                    lit(row["sort_order"]),
                ]
            )
            + ")"
        )

    return f"""create table if not exists public.civil_special_laws (
  id text primary key,
  civil_article text not null,
  civil_article_title text not null,
  category text not null,
  law_name text not null,
  short_name text,
  source_url text,
  slug text,
  sort_order text not null
);

alter table public.civil_special_laws enable row level security;

drop policy if exists "civil special laws readable" on public.civil_special_laws;
create policy "civil special laws readable"
on public.civil_special_laws for select
using (true);

grant select on public.civil_special_laws to anon, authenticated;

delete from public.civil_special_laws;

insert into public.civil_special_laws
  (id, civil_article, civil_article_title, category, law_name, short_name, source_url, slug, sort_order)
values
{",\n".join(values)}
on conflict (id) do update set
  civil_article = excluded.civil_article,
  civil_article_title = excluded.civil_article_title,
  category = excluded.category,
  law_name = excluded.law_name,
  short_name = excluded.short_name,
  source_url = excluded.source_url,
  slug = excluded.slug,
  sort_order = excluded.sort_order;
"""


def main() -> None:
    rows = parse_rows()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    SQL_OUT.write_text(build_sql(rows), encoding="utf-8")
    SQL_ASCII_OUT.write_text(build_sql(rows, ascii_only=True), encoding="ascii")
    print(f"wrote {len(rows)} rows")
    print(JSON_OUT)
    print(SQL_ASCII_OUT)


if __name__ == "__main__":
    main()
